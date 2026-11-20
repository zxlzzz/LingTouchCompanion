// 合成深度场景（只给测试用）：已知高度、俯仰、横滚的相机，看地面、长方体和竖直圆柱。
// 射线方向取自 DepthCameraModel 的去畸变查表；查表本身由 test_depth_geometry 用正向模型单独验证。
#pragma once

#include <cmath>
#include <cstdint>
#include <utility>
#include <vector>

#include "lingtouch/perception/depth_geometry.h"
#include "lingtouch/types.h"

namespace lt_synth {

constexpr double kPi = 3.14159265358979323846;

// 世界坐标：x 右、y 前、z 上；地面 z = 0；相机在 (0, 0, height)。
struct Box {
  double x0, x1, y0, y1, z0, z1;
};

struct Cylinder {  // 竖直圆柱
  double cx, cy, radius, z0, z1;
};

struct Scene {
  bool ground = true;
  std::vector<Box> boxes;
  std::vector<Cylinder> cylinders;
  double max_range_m = 6.0;  // 超出量程的读数为 0（无数据）
};

struct Pose {
  double height_m = 1.5;
  double pitch_deg = 30;  // 光轴向下为正
  double roll_deg = 0;
};

struct Vec {
  double x, y, z;
};

inline Vec add(Vec a, Vec b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec scale(Vec a, double s) { return {a.x * s, a.y * s, a.z * s}; }

inline bool ray_box(Vec o, Vec d, const Box& b, double* t_hit) {
  double tmin = 0.0, tmax = 1e30;
  const double lo[3] = {b.x0, b.y0, b.z0}, hi[3] = {b.x1, b.y1, b.z1};
  const double oo[3] = {o.x, o.y, o.z}, dd[3] = {d.x, d.y, d.z};
  for (int a = 0; a < 3; ++a) {
    if (std::fabs(dd[a]) < 1e-15) {
      if (oo[a] < lo[a] || oo[a] > hi[a]) return false;
      continue;
    }
    double t0 = (lo[a] - oo[a]) / dd[a], t1 = (hi[a] - oo[a]) / dd[a];
    if (t0 > t1) std::swap(t0, t1);
    if (t0 > tmin) tmin = t0;
    if (t1 < tmax) tmax = t1;
    if (tmin > tmax) return false;
  }
  if (tmin <= 1e-9) return false;
  *t_hit = tmin;
  return true;
}

inline bool ray_cylinder(Vec o, Vec d, const Cylinder& c, double* t_hit) {
  bool hit = false;
  double best = 1e30;
  const double ox = o.x - c.cx, oy = o.y - c.cy;
  const double a = d.x * d.x + d.y * d.y;
  if (a > 1e-15) {
    const double b = 2 * (ox * d.x + oy * d.y);
    const double cc = ox * ox + oy * oy - c.radius * c.radius;
    const double disc = b * b - 4 * a * cc;
    if (disc >= 0) {
      const double t = (-b - std::sqrt(disc)) / (2 * a);
      const double z = o.z + t * d.z;
      if (t > 1e-9 && z >= c.z0 && z <= c.z1) {
        best = t;
        hit = true;
      }
    }
  }
  if (std::fabs(d.z) > 1e-15) {  // 顶面
    const double t = (c.z1 - o.z) / d.z;
    const double x = ox + t * d.x, y = oy + t * d.y;
    if (t > 1e-9 && x * x + y * y <= c.radius * c.radius && t < best) {
      best = t;
      hit = true;
    }
  }
  if (hit) *t_hit = best;
  return hit;
}

// 渲染一帧。meaning 决定写进去的是光轴 Z 还是径向距离。
inline lingtouch::DepthFrame render(const Scene& scene, const lingtouch::DepthCameraModel& model, const Pose& pose,
                                    lingtouch::DepthMeaning meaning) {
  const double th = pose.pitch_deg * kPi / 180.0, ph = pose.roll_deg * kPi / 180.0;
  // 相机轴在世界坐标里：先俯仰（绕相机 x 轴），再横滚（绕光轴）
  const Vec x1{1, 0, 0}, y1{0, -std::sin(th), -std::cos(th)}, z1{0, std::cos(th), -std::sin(th)};
  const Vec xc = add(scale(x1, std::cos(ph)), scale(y1, std::sin(ph)));
  const Vec yc = add(scale(y1, std::cos(ph)), scale(x1, -std::sin(ph)));
  const Vec zc = z1;
  const Vec origin{0, 0, pose.height_m};

  lingtouch::DepthFrame f;
  f.width = model.width();
  f.height = model.height();
  f.depth_mm.assign(static_cast<size_t>(f.width) * f.height, 0);
  for (size_t i = 0; i < f.depth_mm.size(); ++i) {
    if (!model.pixel_valid(i)) continue;
    const Vec dir = add(add(scale(xc, model.x(i)), scale(yc, model.y(i))), zc);  // 光轴分量为 1
    double t_best = 1e30;
    bool hit = false;
    if (scene.ground && dir.z < -1e-12) {
      t_best = -origin.z / dir.z;
      hit = true;
    }
    double t = 0;
    for (const Box& b : scene.boxes)
      if (ray_box(origin, dir, b, &t) && t < t_best) {
        t_best = t;
        hit = true;
      }
    for (const Cylinder& c : scene.cylinders)
      if (ray_cylinder(origin, dir, c, &t) && t < t_best) {
        t_best = t;
        hit = true;
      }
    if (!hit) continue;
    const double radial = t_best * std::sqrt(dir.x * dir.x + dir.y * dir.y + dir.z * dir.z);
    if (radial > scene.max_range_m) continue;  // 量程按视线距离算
    const double value = meaning == lingtouch::DepthMeaning::kRadialDistance ? radial : t_best;
    const double mm = std::floor(value * 1000.0 + 0.5);
    if (mm < 1 || mm > 65535) continue;
    f.depth_mm[i] = static_cast<uint16_t>(mm);
  }
  return f;
}

}  // namespace lt_synth
