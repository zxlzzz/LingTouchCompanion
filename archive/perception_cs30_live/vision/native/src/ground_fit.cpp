#include "lingtouch/perception/ground_fit.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>

namespace lingtouch {
namespace {

constexpr double kPi = 3.14159265358979323846;

// 跨平台结果一致的伪随机数（不用 std 分布：分布的实现是平台相关的）。
struct SplitMix64 {
  uint64_t state;
  uint64_t next() {
    uint64_t z = (state += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
  }
};

struct Plane {
  double n[3];
  double d;  // n·P + d = 0；d > 0 表示相机（原点）在法线一侧
  double distance(const Point3& p) const { return n[0] * p.x + n[1] * p.y + n[2] * p.z + d; }
};

void orient_towards_camera(Plane* pl) {
  if (pl->d < 0) {
    pl->n[0] = -pl->n[0];
    pl->n[1] = -pl->n[1];
    pl->n[2] = -pl->n[2];
    pl->d = -pl->d;
  }
}

bool plane_from_points(const Point3& a, const Point3& b, const Point3& c, Plane* out) {
  const double ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z;
  const double vx = c.x - a.x, vy = c.y - a.y, vz = c.z - a.z;
  double nx = uy * vz - uz * vy;
  double ny = uz * vx - ux * vz;
  double nz = ux * vy - uy * vx;
  const double len = std::sqrt(nx * nx + ny * ny + nz * nz);
  if (len < 1e-12) return false;
  nx /= len;
  ny /= len;
  nz /= len;
  *out = Plane{{nx, ny, nz}, -(nx * a.x + ny * a.y + nz * a.z)};
  orient_towards_camera(out);
  return true;
}

// 地面应在相机下方：相机坐标里"上"是 -y。
bool passes_gates(const Plane& pl, const GroundParams& p, double cos_max_tilt) {
  return pl.d >= p.camera_height_min_m && pl.d <= p.camera_height_max_m && -pl.n[1] >= cos_max_tilt;
}

// 3×3 对称矩阵的循环 Jacobi 特征分解（只用加减乘除和 sqrt）。
void jacobi_eigen(double a[3][3], double v[3][3], double w[3]) {
  for (int i = 0; i < 3; ++i)
    for (int j = 0; j < 3; ++j) v[i][j] = i == j ? 1.0 : 0.0;
  for (int sweep = 0; sweep < 64; ++sweep) {
    const double off = a[0][1] * a[0][1] + a[0][2] * a[0][2] + a[1][2] * a[1][2];
    const double diag = a[0][0] * a[0][0] + a[1][1] * a[1][1] + a[2][2] * a[2][2];
    if (off == 0.0 || off <= 1e-30 * diag) break;
    for (int p = 0; p < 2; ++p) {
      for (int q = p + 1; q < 3; ++q) {
        if (a[p][q] == 0.0) continue;
        const double theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
        const double t = (theta >= 0 ? 1.0 : -1.0) / (std::fabs(theta) + std::sqrt(theta * theta + 1.0));
        const double c = 1.0 / std::sqrt(t * t + 1.0);
        const double s = t * c;
        for (int k = 0; k < 3; ++k) {
          const double akp = a[k][p], akq = a[k][q];
          a[k][p] = c * akp - s * akq;
          a[k][q] = s * akp + c * akq;
        }
        for (int k = 0; k < 3; ++k) {
          const double apk = a[p][k], aqk = a[q][k];
          a[p][k] = c * apk - s * aqk;
          a[q][k] = s * apk + c * aqk;
        }
        for (int k = 0; k < 3; ++k) {
          const double vkp = v[k][p], vkq = v[k][q];
          v[k][p] = c * vkp - s * vkq;
          v[k][q] = s * vkp + c * vkq;
        }
      }
    }
  }
  for (int i = 0; i < 3; ++i) w[i] = a[i][i];
}

std::string format_failure(const char* fmt, double a, double b) {
  char buf[200];
  std::snprintf(buf, sizeof(buf), fmt, a, b);
  return buf;
}

}  // namespace

bool fit_plane_least_squares(const std::vector<Point3>& points, std::array<double, 3>* normal, double* offset) {
  if (points.size() < 3) return false;
  double cx = 0, cy = 0, cz = 0;
  for (const Point3& p : points) {
    cx += p.x;
    cy += p.y;
    cz += p.z;
  }
  const double inv = 1.0 / static_cast<double>(points.size());
  cx *= inv;
  cy *= inv;
  cz *= inv;
  double a[3][3] = {{0, 0, 0}, {0, 0, 0}, {0, 0, 0}};
  for (const Point3& p : points) {
    const double dx = p.x - cx, dy = p.y - cy, dz = p.z - cz;
    a[0][0] += dx * dx;
    a[0][1] += dx * dy;
    a[0][2] += dx * dz;
    a[1][1] += dy * dy;
    a[1][2] += dy * dz;
    a[2][2] += dz * dz;
  }
  a[1][0] = a[0][1];
  a[2][0] = a[0][2];
  a[2][1] = a[1][2];
  double v[3][3];
  double w[3];
  jacobi_eigen(a, v, w);
  int smallest = 0;
  for (int i = 1; i < 3; ++i)
    if (w[i] < w[smallest]) smallest = i;
  double nx = v[0][smallest], ny = v[1][smallest], nz = v[2][smallest];
  const double len = std::sqrt(nx * nx + ny * ny + nz * nz);
  if (!(len > 0)) return false;
  nx /= len;
  ny /= len;
  nz /= len;
  *normal = {nx, ny, nz};
  *offset = -(nx * cx + ny * cy + nz * cz);
  return true;
}

GroundEstimate fit_ground_plane(const std::vector<Point3>& candidates, const GroundParams& p) {
  GroundEstimate g;
  const size_t n = candidates.size();
  g.candidates = static_cast<uint32_t>(n);
  if (n < 3 || n < p.min_inliers) {
    g.failure = format_failure("候选点只有 %.0f 个，少于 ground.min_inliers = %.0f", static_cast<double>(n),
                               static_cast<double>(p.min_inliers));
    return g;
  }
  const double cos_max_tilt = std::cos(p.max_tilt_deg * kPi / 180.0);

  SplitMix64 rng{p.ransac_seed};
  Plane best{{0, 0, 0}, 0};
  size_t best_count = 0;
  for (int it = 0; it < p.ransac_iterations; ++it) {
    const size_t i = static_cast<size_t>(rng.next() % n);
    const size_t j = static_cast<size_t>(rng.next() % n);
    const size_t k = static_cast<size_t>(rng.next() % n);
    if (i == j || j == k || i == k) continue;
    Plane pl;
    if (!plane_from_points(candidates[i], candidates[j], candidates[k], &pl)) continue;
    if (!passes_gates(pl, p, cos_max_tilt)) continue;
    size_t count = 0;
    for (const Point3& q : candidates)
      if (std::fabs(pl.distance(q)) <= p.inlier_distance_m) ++count;
    if (count > best_count) {
      best = pl;
      best_count = count;
    }
  }
  if (best_count < 3) {
    g.failure = "没有找到满足相机高度和倾角条件的平面";
    return g;
  }

  std::vector<Point3> inliers;
  inliers.reserve(best_count);
  for (const Point3& q : candidates)
    if (std::fabs(best.distance(q)) <= p.inlier_distance_m) inliers.push_back(q);
  std::array<double, 3> normal{};
  double offset = 0;
  if (!fit_plane_least_squares(inliers, &normal, &offset)) {
    g.failure = "最小二乘精修失败";
    return g;
  }
  Plane refined{{normal[0], normal[1], normal[2]}, offset};
  orient_towards_camera(&refined);
  g.normal = {refined.n[0], refined.n[1], refined.n[2]};
  g.height_m = refined.d;
  g.pitch_deg = std::asin(std::fmax(-1.0, std::fmin(1.0, -refined.n[2]))) * 180.0 / kPi;
  g.roll_deg = std::atan2(refined.n[0], -refined.n[1]) * 180.0 / kPi;

  if (!passes_gates(refined, p, cos_max_tilt)) {
    g.failure = format_failure("精修后的平面不满足条件（高度 %.3f m，与相机向上方向夹角的余弦 %.3f）", refined.d,
                               -refined.n[1]);
    return g;
  }

  // 精修平面的内点、残差、沿前向的铺开长度
  const double fx = -refined.n[2] * refined.n[0];
  const double fy = -refined.n[2] * refined.n[1];
  const double fz = 1.0 - refined.n[2] * refined.n[2];
  const double flen = std::sqrt(fx * fx + fy * fy + fz * fz);
  size_t count = 0;
  size_t below = 0;
  double sum_sq = 0;
  double fmin = 0, fmax = 0;
  for (const Point3& q : candidates) {
    const double dist = refined.distance(q);
    if (dist < -p.below_margin_m) ++below;
    if (std::fabs(dist) > p.inlier_distance_m) continue;
    const double f = (fx * q.x + fy * q.y + fz * q.z) / flen;
    if (count == 0 || f < fmin) fmin = f;
    if (count == 0 || f > fmax) fmax = f;
    sum_sq += dist * dist;
    ++count;
  }
  g.inliers = static_cast<uint32_t>(count);
  g.rms_m = count > 0 ? std::sqrt(sum_sq / static_cast<double>(count)) : 0.0;
  if (count < p.min_inliers) {
    g.failure = format_failure("地面内点 %.0f 个，少于 ground.min_inliers = %.0f", static_cast<double>(count),
                               static_cast<double>(p.min_inliers));
    return g;
  }
  if (fmax - fmin < p.min_forward_span_m) {
    g.failure = format_failure("地面内点沿前向只铺开 %.2f m，少于 ground.min_forward_span_m = %.2f", fmax - fmin,
                               p.min_forward_span_m);
    return g;
  }
  const double below_fraction = static_cast<double>(below) / static_cast<double>(n);
  if (below_fraction > p.max_below_fraction) {
    g.failure = format_failure("%.1f%% 的点低于拟合平面 %.2f m 以上，拟合到的可能不是地面（例如桌面）",
                               below_fraction * 100.0, p.below_margin_m);
    return g;
  }
  g.ok = true;
  return g;
}

GroundEstimate PlaneFitGroundPose::estimate(const std::vector<Point3>& camera_points, const ImuSample* imu) {
  (void)imu;  // 第一阶段不用 IMU
  return fit_ground_plane(camera_points, params_);
}

GroundFrame make_ground_frame(const GroundEstimate& ground, bool image_mirrored) {
  GroundFrame f;
  const double nx = ground.normal[0], ny = ground.normal[1], nz = ground.normal[2];
  f.up = {nx, ny, nz};
  // 前向 = 光轴 (0,0,1) 去掉沿法线的分量
  double fx = -nz * nx, fy = -nz * ny, fz = 1.0 - nz * nz;
  const double len = std::sqrt(fx * fx + fy * fy + fz * fz);
  fx /= len;
  fy /= len;
  fz /= len;
  f.forward = {fx, fy, fz};
  // 右 = 前 × 上
  f.right = {fy * nz - fz * ny, fz * nx - fx * nz, fx * ny - fy * nx};
  f.height = ground.height_m;
  f.mirror_x = image_mirrored;
  return f;
}

}  // namespace lingtouch
