#include "lingtouch/depth_evidence.h"
#include "lingtouch/report_json.h"
namespace depth_sim {
using namespace lingtouch;
Result<std::string> binary_json(const std::array<uint8_t,54>& counts, int k) {
  if (k < 1 || k > 16) return Result<std::string>::failure("K must be 1..16");
  std::string out = "[";
  for (int r=0;r<6;++r) {
    if(r) out+=",";
    out+="[";
    for(int c=0;c<9;++c) {
      const auto n=counts[r*9+c];
      if(n>16) return Result<std::string>::failure("Invalid subcell count");
      if(c) out+=",";
      out+=n>=k?"1":"0";
    }
    out+="]";
  }
  return Result<std::string>::success(out+"]");
}
template<size_t N> std::string array_json(const std::array<uint8_t,N>& a) {
  std::string s="[";
  for(size_t i=0;i<N;++i) {if(i)s+=",";s+=std::to_string(a[i]);}
  return s+"]";
}
std::string evidence_json(const OccupancyGrid& g, bool connected) {
  std::string s=grid_json(g,monotonic_now_ns());
  s.pop_back();
  s+=",\"connected\":"+std::string(connected?"true":"false");
  s+=",\"ground_valid\":"+std::string(connected&&g.status==GridStatus::kOk&&g.ground.ok?"true":"false");
  s+=",\"evidence\":{\"schema_version\":1,\"obstacle\":"+array_json(g.evidence.obstacle);
  s+=",\"ground\":"+array_json(g.evidence.ground)+",\"unknown\":"+array_json(g.evidence.unknown);
  s+=",\"fine_near_first\":"+array_json(g.evidence.fine)+"}}";
  return s;
}
}
