#include "lingtouch/perception/depth_review.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <limits>
#include <map>
#include <numeric>

#include "lingtouch/perception/ground_fit.h"

namespace lingtouch {
namespace {
constexpr int kFineCols = 36, kFineRows = 24, kFine = kFineCols * kFineRows;
constexpr int64_t kHistoryNs = 2200000000LL;
using V = Point3;
using M = std::array<V, 3>;  // columns
V add(V a, V b) { return {a.x+b.x,a.y+b.y,a.z+b.z}; }
V mul(V a, double b) { return {a.x*b,a.y*b,a.z*b}; }
V sub(V a, V b) { return add(a,mul(b,-1)); }
double dot(V a,V b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
V cross(V a,V b) { return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x}; }
double norm(V p) { return std::sqrt(dot(p,p)); }
V rotate(const M& r,V p) { return add(add(mul(r[0],p.x),mul(r[1],p.y)),mul(r[2],p.z)); }
V inverse_rotate(const M& r,V p) { return {dot(r[0],p),dot(r[1],p),dot(r[2],p)}; }
V as_point(const std::array<double,3>& p) { return {p[0],p[1],p[2]}; }
double axis(V p,int a) { return a==0?p.x:a==1?p.y:p.z; }
struct Surface { V point, normal; };
struct Observation {
  int64_t time = 0;
  std::vector<V> xyz;
  std::vector<uint8_t> valid, suspect, trusted;
  std::vector<Surface> cloud;
  GroundEstimate ground;
  DepthMask quality;
};

// Integral rows of elliptical dilations. Each member contributes a horizontal
// interval per row. This keeps the cost proportional to the measured pixels.
void add_halo(std::vector<int>& rows, int width, int height, int x, int y, int radius) {
  for (int dy=-radius;dy<=radius;++dy) {
    if (y+dy<0 || y+dy>=height) continue;
    const int dx=static_cast<int>(std::lround(std::sqrt(radius*radius-dy*dy)));
    const int offset=(y+dy)*(width+1);
    ++rows[offset+std::max(0,x-dx)];
    --rows[offset+std::min(width,x+dx+1)];
  }
}

std::vector<uint8_t> mark_suspects(const DepthFrame& f,const DepthCameraModel& camera,
                                  const DepthParams& params,const Observation& obs) {
  const int w=f.width,h=f.height,n=w*h;
  constexpr int radius=14;
  std::vector<uint8_t> visited(n),suspect(n);
  std::vector<int> component;
  std::vector<double> values,context;
  const auto eligible=[&](int i) { return obs.valid[i] && obs.xyz[i].z <= 1.8; };
  for(int seed=0;seed<n;++seed) {
    if(visited[seed]||!eligible(seed)) continue;
    component.clear();component.push_back(seed);visited[seed]=1;
    int x0=seed%w,x1=x0,y0=seed/w,y1=y0;
    for(size_t k=0;k<component.size();++k) {
      const int i=component[k],x=i%w,y=i/w;
      x0=std::min(x0,x);x1=std::max(x1,x);y0=std::min(y0,y);y1=std::max(y1,y);
      for(int yy=std::max(0,y-1);yy<=std::min(h-1,y+1);++yy) {
        for(int xx=std::max(0,x-1);xx<=std::min(w-1,x+1);++xx) {
          const int j=yy*w+xx;
          if(visited[j]||!eligible(j)) continue;
          const double a=obs.xyz[i].z,b=obs.xyz[j].z;
          if(std::abs(a-b)<=std::max(.035,.025*std::min(a,b))) {
            visited[j]=1;component.push_back(j);
          }
        }
      }
    }
    if(component.size()<12) continue;
    x0=std::max(0,x0-radius);y0=std::max(0,y0-radius);
    x1=std::min(w-1,x1+radius);y1=std::min(h-1,y1+radius);
    const int rw=x1-x0+1,rh=y1-y0+1;
    std::vector<int> outer((rw+1)*rh),inner((rw+1)*rh);
    for(int i:component) {
      add_halo(outer,rw,rh,i%w-x0,i/w-y0,radius);
      add_halo(inner,rw,rh,i%w-x0,i/w-y0,2);
    }
    int halo=0;context.clear();
    for(int y=0;y<rh;++y) {
      int outside=0,inside=0;
      for(int x=0;x<rw;++x) {
        outside+=outer[y*(rw+1)+x];inside+=inner[y*(rw+1)+x];
        if(!outside||inside) continue;
        ++halo;
        const int i=(y+y0)*w+x+x0;
        if(f.depth_mm[i]>=params.min_valid_mm && f.depth_mm[i]<=params.max_valid_mm && camera.pixel_valid(i))
          context.push_back(backproject(camera,i,f.depth_mm[i],params.meaning).z);
      }
    }
    if(halo<24) continue;
    const double invalid=1.0-static_cast<double>(context.size())/halo;
    bool flag=invalid>=.78;
    if(!flag && invalid>=.60 && context.size()>=24) {
      values.clear();for(int i:component) values.push_back(obs.xyz[i].z);
      auto mid=values.begin()+values.size()/2;
      auto far=context.begin()+context.size()/2;
      std::nth_element(values.begin(),mid,values.end());
      std::nth_element(context.begin(),far,context.end());
      flag=*far-*mid>=.25;
    }
    if(flag) for(int i:component) suspect[i]=1;
  }
  return suspect;
}

Observation observe(const DepthFrame& f,const DepthCameraModel& camera,const Config& config) {
  Observation out;
  out.time=f.capture_time_ns;
  compute_depth_mask(f,camera,config.depth,&out.quality);
  out.valid=out.quality.valid;
  out.xyz.resize(f.depth_mm.size());
  for(size_t i=0;i<out.xyz.size();++i) if(out.valid[i])
    out.xyz[i]=backproject(camera,i,f.depth_mm[i],config.depth.meaning);
  out.suspect=mark_suspects(f,camera,config.depth,out);
  const int w=f.width,h=f.height;
  out.trusted.resize(out.valid.size());
  const auto clean=[&](int i) { return out.valid[i] && !out.suspect[i]; };
  for(int y=0;y<h;++y) for(int x=0;x<w;++x) {
    const int i=y*w+x;
    if(!clean(i)) continue;
    int support=0;
    for(int yy=std::max(0,y-1);yy<=std::min(h-1,y+1);++yy)
      for(int xx=std::max(0,x-1);xx<=std::min(w-1,x+1);++xx) {
        const int j=yy*w+xx;
        if(j!=i && clean(j) && std::abs(out.xyz[i].z-out.xyz[j].z)<=.04) ++support;
      }
    out.trusted[i]=support>=2;
  }
  std::vector<V> ground_samples;
  const int step=config.ground.sample_stride_px;
  for(int y=0;y<h;y+=step) for(int x=0;x<w;x+=step)
    if(clean(y*w+x)) ground_samples.push_back(out.xyz[y*w+x]);
  out.ground=fit_ground_plane(ground_samples,config.ground);
  std::map<std::array<int,3>,Surface> voxels;
  for(int y=2;y<h-2;y+=5) for(int x=2;x<w-2;x+=5) {
    const int i=y*w+x;
    if(!out.trusted[i]) continue;
    const V p=out.xyz[i];
    bool good=true;
    for(int j:{i-2,i+2,i-2*w,i+2*w})
      good=good && out.trusted[j] && std::abs(out.xyz[j].z-p.z)<=std::max(.06,.035*p.z);
    if(!good) continue;
    const V n=cross(sub(out.xyz[i+2],out.xyz[i-2]),sub(out.xyz[i+2*w],out.xyz[i-2*w]));
    const double length=norm(n);
    if(length<1e-7) continue;
    const std::array<int,3> key{static_cast<int>(std::floor(p.x/.055)),
        static_cast<int>(std::floor(p.y/.055)),static_cast<int>(std::floor(p.z/.055))};
    voxels.emplace(key,Surface{p,mul(n,1/length)});
  }
  for(const auto& entry:voxels) out.cloud.push_back(entry.second);
  return out;
}

class SearchTree {
 public:
  explicit SearchTree(const std::vector<Surface>& cloud):cloud_(cloud),indices_(cloud.size()) {
    std::iota(indices_.begin(),indices_.end(),0);
    build(0,static_cast<int>(indices_.size()),0);
  }
  int nearest(V p,double limit) const {
    int best=-1;double square=limit*limit;
    find(p,0,static_cast<int>(indices_.size()),0,&square,&best);
    return best;
  }
 private:
  void build(int lo,int hi,int a) {
    if(hi-lo<2) return;
    const int mid=(lo+hi)/2;
    std::nth_element(indices_.begin()+lo,indices_.begin()+mid,indices_.begin()+hi,[&](int i,int j) {
      return axis(cloud_[i].point,a)<axis(cloud_[j].point,a);
    });
    build(lo,mid,(a+1)%3);build(mid+1,hi,(a+1)%3);
  }
  void find(V p,int lo,int hi,int a,double* square,int* best) const {
    if(lo==hi) return;
    const int mid=(lo+hi)/2,i=indices_[mid];
    const V delta=sub(p,cloud_[i].point);
    const double d=dot(delta,delta),split=axis(delta,a);
    if(d<*square){*square=d;*best=i;}
    const int next=(a+1)%3;
    if(split<0) {
      find(p,lo,mid,next,square,best);
      if(split*split<*square)find(p,mid+1,hi,next,square,best);
    } else {
      find(p,mid+1,hi,next,square,best);
      if(split*split<*square)find(p,lo,mid,next,square,best);
    }
  }
  const std::vector<Surface>& cloud_;
  std::vector<int> indices_;
};

bool solve(double a[6][7],double delta[6]) {
  double largest=0,smallest=std::numeric_limits<double>::max();
  for(int i=0;i<6;++i) {
    int row=i;
    for(int j=i+1;j<6;++j) if(std::abs(a[j][i])>std::abs(a[row][i])) row=j;
    for(int j=i;j<7;++j)std::swap(a[row][j],a[i][j]);
    const double pivot=std::abs(a[i][i]);
    if(pivot<1e-8) return false;
    largest=std::max(largest,pivot);smallest=std::min(smallest,pivot);
    for(int j=i+1;j<6;++j) {
      const double factor=a[j][i]/a[i][i];
      for(int k=i;k<7;++k)a[j][k]-=factor*a[i][k];
    }
  }
  if(smallest<largest*.000324) return false;
  for(int i=5;i>=0;--i) {
    double sum=a[i][6];for(int j=i+1;j<6;++j)sum-=a[i][j]*delta[j];
    delta[i]=sum/a[i][i];
  }
  return true;
}

V rotation_update(V p,V change) {
  const double angle=norm(change);
  if(angle<1e-10)return add(p,cross(change,p));
  const V unit=mul(change,1/angle);
  return add(add(mul(p,std::cos(angle)),mul(cross(unit,p),std::sin(angle))),
             mul(unit,dot(unit,p)*(1-std::cos(angle))));
}

double measured_z(V p,const Observation& frame,const DepthCameraModel& camera) {
  if(p.z<=.1 || !std::isfinite(p.z))return 0;
  double u,v;camera.project(p.x/p.z,p.y/p.z,&u,&v);
  if(u<-.5||v<-.5||u>=camera.width()-.5||v>=camera.height()-.5)return 0;
  const long x=std::lround(u),y=std::lround(v);
  if(x<0||y<0||x>=camera.width()||y>=camera.height())return 0;
  const size_t i=static_cast<size_t>(y)*camera.width()+x;
  return frame.trusted[i]?frame.xyz[i].z:0;
}

struct Pose { M r; V t; };
bool fit_pose(const Observation& from,const Observation& to,const DepthCameraModel& camera,Pose* pose) {
  if(!from.ground.ok||!to.ground.ok||from.cloud.size()<180||to.cloud.size()<180)return false;
  const GroundFrame a=make_ground_frame(from.ground,false),b=make_ground_frame(to.ground,false);
  const M ab{as_point(a.right),as_point(a.forward),as_point(a.up)},bb{as_point(b.right),as_point(b.forward),as_point(b.up)};
  for(int i=0;i<3;++i) {
    const V unit{double(i==0),double(i==1),double(i==2)};
    pose->r[i]=rotate(bb,inverse_rotate(ab,unit));
  }
  pose->t=mul(as_point(b.up),from.ground.height_m-to.ground.height_m);
  const SearchTree target(to.cloud),source(from.cloud);
  for(double gate:{.30,.17,.09}) for(int iter=0;iter<5;++iter) {
    double normal[6][7]{};
    int matched=0;
    for(const auto& s:from.cloud) {
      const V p=add(rotate(pose->r,s.point),pose->t);
      const int j=target.nearest(p,gate);
      if(j<0)continue;
      const auto& q=to.cloud[j];
      if(dot(rotate(pose->r,s.normal),q.normal)<.78)continue;
      const double residual=dot(sub(p,q.point),q.normal);
      const double weight=1/(1+(residual/.04)*(residual/.04));
      const V turn=cross(p,q.normal);
      const double jac[]{turn.x,turn.y,turn.z,q.normal.x,q.normal.y,q.normal.z};
      for(int r=0;r<6;++r) {
        for(int c=0;c<6;++c)normal[r][c]+=weight*jac[r]*jac[c];
        normal[r][6]-=weight*jac[r]*residual;
      }
      ++matched;
    }
    double delta[6]{};
    if(matched<140||!solve(normal,delta))return false;
    const V change{delta[0],delta[1],delta[2]},shift{delta[3],delta[4],delta[5]};
    if(norm(change)>.35||norm(shift)>.35)return false;
    for(auto& column:pose->r)column=rotation_update(column,change);
    pose->t=add(rotation_update(pose->t,change),shift);
    if(norm(change)+norm(shift)<.0007)break;
  }
  const double cosine=(pose->r[0].x+pose->r[1].y+pose->r[2].z-1)/2;
  const double move=norm(pose->t);
  if(move<.04||move>.70||cosine<.848)return false;
  auto check=[&](const Observation& samples,const Observation& reference,const SearchTree& tree,bool reverse) {
    size_t overlap=0,measured=0,agree=0;
    for(const auto& s:samples.cloud) {
      const V p=reverse?inverse_rotate(pose->r,sub(s.point,pose->t)):add(rotate(pose->r,s.point),pose->t);
      overlap+=tree.nearest(p,.09)>=0;
      const double z=measured_z(p,reference,camera);
      if(z>0){++measured;agree+=std::abs(z-p.z)<=.09;}
    }
    return overlap>=.32*samples.cloud.size() && measured>=160 && agree>=.69*measured;
  };
  return check(from,to,target,false)&&check(to,from,source,true);
}

int cell_for(const GroundPoint& p) {
  if(p.x< -1.8||p.x>=1.8||p.y<1.0||p.y>=3.4)return -1;
  const int sx=std::clamp(static_cast<int>((p.x+1.8)*10),0,kFineCols-1);
  const int sy=std::clamp(static_cast<int>((p.y-1)*10),0,kFineRows-1);
  return sy*kFineCols+sx;
}

void add_yolo_evidence(const std::vector<std::vector<uint8_t>>& masks,const Observation& obs,
                       const std::vector<int>& ids,const std::vector<float>& heights,int width,
                       std::array<bool,kFine>* yolo) {
  for(const auto& mask:masks) {
    if(mask.size()!=ids.size())continue;
    std::vector<size_t> points,seeds;
    for(size_t i=0;i<mask.size();++i) {
      if(!mask[i]||!(heights[i]>=.08f&&heights[i]<=1.9f))continue;
      points.push_back(i);
      if(i>=static_cast<size_t>(width)&&i+width<mask.size()&&i%width>0&&i%width<static_cast<size_t>(width-1)&&
          mask[i-1]&&mask[i+1]&&mask[i-width]&&mask[i+width])seeds.push_back(i);
    }
    if(points.size()<16)continue;
    if(seeds.size()<16)seeds=points;
    std::array<int,65> hist{};
    auto bin=[&](size_t i){return std::clamp(static_cast<int>(obs.xyz[i].z/.08),0,64);};
    for(size_t i:seeds)++hist[bin(i)];
    int peak=0,best=-1;
    for(int j=0;j<65;++j){const int v=hist[j]+(j>0?hist[j-1]:0)+(j<64?hist[j+1]:0);if(v>best){best=v;peak=j;}}
    std::vector<double> z;
    for(size_t i:seeds)if(std::abs(bin(i)-peak)<=1)z.push_back(obs.xyz[i].z);
    if(z.empty())continue;
    const auto middle=z.begin()+z.size()/2;
    std::nth_element(z.begin(),middle,z.end());
    std::array<int,kFine> counts{};int support=0;
    for(size_t i:points)if(std::abs(obs.xyz[i].z-*middle)<=.18){++support;if(ids[i]>=0)++counts[ids[i]];}
    if(support>=16)for(int j=0;j<kFine;++j)if(counts[j]>=3)(*yolo)[j]=true;
  }
}
}  // namespace

struct DepthReview::State { Config config; std::deque<Observation> history; };
DepthReview::DepthReview(const Config& config):state_(std::make_unique<State>()) {state_->config=config;}
DepthReview::~DepthReview()=default;

OccupancyGrid DepthReview::process(const DepthFrame& frame,const DepthCameraModel& camera,
                                  const std::vector<std::vector<uint8_t>>& masks,
                                  const std::vector<DepthFrame>* recent) {
  OccupancyGrid g;
  g.source_frame_id=frame.frame_id;g.capture_time_ns=frame.capture_time_ns;g.intrinsics_id=camera.intrinsics().id;
  Observation now=observe(frame,camera,state_->config);
  g.counts.pixels=static_cast<uint32_t>(now.valid.size());
  g.counts.value_valid=now.quality.value_valid;g.counts.after_wrap=now.quality.after_wrap;
  g.counts.after_flying=now.quality.after_flying;
  g.ground=now.ground;
  g.status=now.ground.ok?GridStatus::kOk:GridStatus::kGroundFitFailed;
  if(now.ground.ok) {
    std::vector<size_t> suspects;
    for(size_t i=0;i<now.suspect.size();++i)if(now.suspect[i])suspects.push_back(i);
    g.counts.suspect=static_cast<uint32_t>(suspects.size());
    std::vector<uint8_t> support(suspects.size()),conflict(suspects.size());
    auto time_ok=[&](int64_t time){return time>0&&time<now.time&&now.time-time<=kHistoryNs;};
    auto vote=[&](const Observation& previous) {
      Pose pose{};
      if(!fit_pose(previous,now,camera,&pose))return;
      ++g.counts.aligned_views;
      for(size_t j=0;j<suspects.size();++j) {
        const V p=now.xyz[suspects[j]];
        if(norm(cross(mul(p,1/norm(p)),pose.t))<.03)continue;
        const V prev=inverse_rotate(pose.r,sub(p,pose.t));
        const double z=measured_z(prev,previous,camera);
        if(z<=0)continue;
        support[j]+=std::abs(z-prev.z)<=std::max(.07,.025*prev.z);
        conflict[j]+=z-prev.z>=.25;
      }
    };
    if(!suspects.empty()) {
      if(recent) {
        for(const auto& earlier:*recent) if(time_ok(earlier.capture_time_ns)&&earlier.width==frame.width&&earlier.height==frame.height)
          vote(observe(earlier,camera,state_->config));
      } else {
        for(const auto& earlier:state_->history)if(time_ok(earlier.time))vote(earlier);
      }
    }
    std::vector<uint8_t> allowed=now.valid;
    for(size_t j=0;j<suspects.size();++j) {
      allowed[suspects[j]]=support[j]>conflict[j];
      g.counts.confirmed+=allowed[suspects[j]];
      g.counts.conflicts+=conflict[j]>0&&support[j]==0;
    }
    const auto ground=make_ground_frame(now.ground,state_->config.depth.image_mirrored);
    std::array<int,kFine> geometric{};
    std::array<bool,kFine> floor{},uncertain{},yolo{};
    std::vector<int> ids(allowed.size(),-1);
    std::vector<float> heights(allowed.size(),-10);
    for(size_t i=0;i<allowed.size();++i) {
      if(!now.valid[i])continue;
      const GroundPoint p=ground.to_ground(now.xyz[i]);
      const int j=cell_for(p);
      if(!allowed[i]){if(j>=0)uncertain[j]=true;continue;}
      ids[i]=j;heights[i]=static_cast<float>(p.z);
      if(j<0)continue;
      ++g.counts.in_grid;
      if(p.z>=.15&&p.z<=1.9)++geometric[j];
      if(std::abs(p.z)<=.05)floor[j]=true;
      if(p.z>.05&&p.z<=1.9)uncertain[j]=true;
    }
    if(!masks.empty())add_yolo_evidence(masks,now,ids,heights,frame.width,&yolo);
    g.evidence.unknown.fill(0);
    for(int j=0;j<kFine;++j) {
      const int cell=(5-j/kFineCols/4)*9+(j%kFineCols)/4;
      if(geometric[j]>=4||yolo[j]){g.evidence.fine[j]=1;++g.evidence.obstacle[cell];}
      else if(floor[j]&&!uncertain[j]){g.evidence.fine[j]=2;++g.evidence.ground[cell];}
      else ++g.evidence.unknown[cell];
      g.counts.yolo_subcells+=yolo[j];
    }
    for(int i=0;i<kGridCells;++i)g.cells[i]=g.evidence.obstacle[i]?CellState::kOccupied:
        g.evidence.ground[i]==16?CellState::kFree:CellState::kUnknown;
  }
  if(!recent) {
    if(state_->history.size()==2)state_->history.pop_front();
    state_->history.push_back(std::move(now));
  }
  return g;
}
}  // namespace lingtouch
