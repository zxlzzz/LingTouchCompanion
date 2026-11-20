#include "lingtouch/perception/depth_geometry.h"

#include <cmath>
#include <cstdlib>

namespace lingtouch {
namespace {

double radial_factor(const CameraIntrinsics& k, double r2) { return 1.0 + ((k.k3 * r2 + k.k2) * r2 + k.k1) * r2; }

// g(r) = r·(1 + k1 r² + k2 r⁴ + k3 r⁶)：径向畸变后的半径
double distorted_radius(const CameraIntrinsics& k, double r) { return r * radial_factor(k, r * r); }

// 径向函数第一个极大值处的未畸变半径；一直单调就取 4.0（约 76° 半视场，超过 CS30 视场）。
double invertible_radius(const CameraIntrinsics& k) {
  const double kStep = 1e-4;
  const double kLimit = 4.0;
  double prev = 0.0;
  for (double r = kStep; r <= kLimit; r += kStep) {
    const double g = distorted_radius(k, r);
    if (g <= prev) return r - kStep;
    prev = g;
  }
  return kLimit;
}

void distort(const CameraIntrinsics& k, double x, double y, double* xd, double* yd) {
  const double r2 = x * x + y * y;
  const double rad = radial_factor(k, r2);
  *xd = x * rad + 2.0 * k.p1 * x * y + k.p2 * (r2 + 2.0 * x * x);
  *yd = y * rad + k.p1 * (r2 + 2.0 * y * y) + 2.0 * k.p2 * x * y;
}

// 先只按径向部分二分求初值，再用含切向项的二维牛顿法收敛。
bool undistort_point(const CameraIntrinsics& k, double r_max, double g_max, double xd, double yd, double* xu,
                     double* yu) {
  const double rd = std::sqrt(xd * xd + yd * yd);
  if (rd >= g_max) return false;
  double x = xd;
  double y = yd;
  if (rd > 0) {
    double lo = 0.0;
    double hi = r_max;
    for (int i = 0; i < 60; ++i) {
      const double mid = 0.5 * (lo + hi);
      if (distorted_radius(k, mid) < rd) lo = mid;
      else hi = mid;
    }
    const double ru = 0.5 * (lo + hi);
    x = xd * (ru / rd);
    y = yd * (ru / rd);
  }
  for (int iter = 0; iter < 20; ++iter) {
    double fx = 0, fy = 0;
    distort(k, x, y, &fx, &fy);
    fx -= xd;
    fy -= yd;
    const double r2 = x * x + y * y;
    const double rad = radial_factor(k, r2);
    const double drad = k.k1 + 2.0 * k.k2 * r2 + 3.0 * k.k3 * r2 * r2;  // d(rad)/d(r²)
    const double j11 = rad + 2.0 * x * x * drad + 2.0 * k.p1 * y + 6.0 * k.p2 * x;
    const double j12 = 2.0 * x * y * drad + 2.0 * k.p1 * x + 2.0 * k.p2 * y;
    const double j22 = rad + 2.0 * y * y * drad + 6.0 * k.p1 * y + 2.0 * k.p2 * x;
    const double det = j11 * j22 - j12 * j12;  // 雅可比矩阵对称：dX/dy == dY/dx
    if (std::fabs(det) < 1e-9) return false;
    const double dx = (j22 * fx - j12 * fy) / det;
    const double dy = (j11 * fy - j12 * fx) / det;
    x -= dx;
    y -= dy;
    if (std::fabs(dx) + std::fabs(dy) < 1e-15) break;
  }
  double ex = 0, ey = 0;
  distort(k, x, y, &ex, &ey);
  if (std::fabs(ex - xd) > 1e-9 || std::fabs(ey - yd) > 1e-9) return false;
  if (x * x + y * y >= r_max * r_max) return false;
  *xu = x;
  *yu = y;
  return true;
}

}  // namespace

Result<DepthCameraModel> DepthCameraModel::create(const CameraIntrinsics& intrinsics, bool undistort) {
  if (intrinsics.width <= 0 || intrinsics.height <= 0 || !(intrinsics.fx > 0) || !(intrinsics.fy > 0))
    return Result<DepthCameraModel>::failure("内参不完整");
  DepthCameraModel m;
  m.intrinsics_ = intrinsics;
  m.undistort_ = undistort;
  const size_t n = static_cast<size_t>(intrinsics.width) * static_cast<size_t>(intrinsics.height);
  m.x_.assign(n, 0.0f);
  m.y_.assign(n, 0.0f);
  m.inv_norm_.assign(n, 0.0f);
  m.valid_.assign(n, 0);
  const double r_max = undistort ? invertible_radius(intrinsics) : 0.0;
  const double g_max = undistort ? distorted_radius(intrinsics, r_max) : 0.0;
  for (int v = 0; v < intrinsics.height; ++v) {
    for (int u = 0; u < intrinsics.width; ++u) {
      const size_t i = static_cast<size_t>(v) * static_cast<size_t>(intrinsics.width) + static_cast<size_t>(u);
      // 像素中心约定与 OpenCV 相同：像素 (u, v) 的坐标就是 (u, v)
      const double xd = (u - intrinsics.cx) / intrinsics.fx;
      const double yd = (v - intrinsics.cy) / intrinsics.fy;
      double xu = xd;
      double yu = yd;
      if (undistort && !undistort_point(intrinsics, r_max, g_max, xd, yd, &xu, &yu)) {
        ++m.invalid_pixels_;
        continue;
      }
      m.x_[i] = static_cast<float>(xu);
      m.y_[i] = static_cast<float>(yu);
      m.inv_norm_[i] = static_cast<float>(1.0 / std::sqrt(xu * xu + yu * yu + 1.0));
      m.valid_[i] = 1;
    }
  }
  return Result<DepthCameraModel>::success(std::move(m));
}

void DepthCameraModel::project(double xn, double yn, double* u, double* v) const {
  double xd = xn;
  double yd = yn;
  if (undistort_) distort(intrinsics_, xn, yn, &xd, &yd);
  *u = intrinsics_.cx + intrinsics_.fx * xd;
  *v = intrinsics_.cy + intrinsics_.fy * yd;
}

void compute_depth_mask(const DepthFrame& frame, const DepthCameraModel& model, const DepthParams& p,
                        DepthMask* mask) {
  const int w = frame.width;
  const int h = frame.height;
  const size_t n = static_cast<size_t>(w) * static_cast<size_t>(h);
  std::vector<uint8_t>& valid = mask->valid;
  valid.assign(n, 0);
  const uint16_t* d = frame.depth_mm.data();

  uint32_t count = 0;
  for (size_t i = 0; i < n; ++i) {
    const uint32_t z = d[i];
    const bool ok = z != 0 && !(p.reject_value_one && z == 1) && z >= p.min_valid_mm && z <= p.max_valid_mm &&
                    model.pixel_valid(i);
    valid[i] = ok ? 1 : 0;
    count += ok ? 1 : 0;
  }
  mask->value_valid = count;

  // 疑似相位绕回：近点四周 (2r+1)² 窗口里无效像素占比过高 → 无效。基于上一步的掩膜计算。
  if (p.wrap_window_radius_px > 0) {
    const int r = p.wrap_window_radius_px;
    std::vector<uint32_t> integral((static_cast<size_t>(w) + 1) * (static_cast<size_t>(h) + 1), 0);
    const size_t stride = static_cast<size_t>(w) + 1;
    for (int y = 0; y < h; ++y) {
      uint32_t row = 0;
      for (int x = 0; x < w; ++x) {
        row += valid[static_cast<size_t>(y) * w + x] ? 0u : 1u;
        integral[(y + 1) * stride + (x + 1)] = integral[y * stride + (x + 1)] + row;
      }
    }
    std::vector<uint8_t> drop(n, 0);
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < w; ++x) {
        const size_t i = static_cast<size_t>(y) * w + x;
        if (!valid[i] || d[i] > p.wrap_max_depth_mm) continue;
        const int x0 = x - r < 0 ? 0 : x - r;
        const int y0 = y - r < 0 ? 0 : y - r;
        const int x1 = x + r + 1 > w ? w : x + r + 1;
        const int y1 = y + r + 1 > h ? h : y + r + 1;
        const uint32_t invalid = integral[y1 * stride + x1] - integral[y0 * stride + x1] -
                                 integral[y1 * stride + x0] + integral[y0 * stride + x0];
        const double total = static_cast<double>((x1 - x0) * (y1 - y0));
        if (static_cast<double>(invalid) >= p.wrap_invalid_fraction * total) drop[i] = 1;
      }
    }
    for (size_t i = 0; i < n; ++i)
      if (drop[i]) {
        valid[i] = 0;
        --count;
      }
  }
  mask->after_wrap = count;

  // 边缘飞点：3×3 邻域里深度一致的有效邻居太少 → 丢掉。基于绕回过滤后的掩膜计算。
  if (p.flying_min_consistent_neighbors > 0) {
    std::vector<uint8_t> drop(n, 0);
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < w; ++x) {
        const size_t i = static_cast<size_t>(y) * w + x;
        if (!valid[i]) continue;
        const double zi = d[i];
        double tol = p.flying_rel_tolerance * zi;
        if (tol < static_cast<double>(p.flying_abs_tolerance_mm)) tol = static_cast<double>(p.flying_abs_tolerance_mm);
        int consistent = 0;
        for (int dy = -1; dy <= 1; ++dy) {
          for (int dx = -1; dx <= 1; ++dx) {
            if (dx == 0 && dy == 0) continue;
            const int xx = x + dx;
            const int yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
            const size_t j = static_cast<size_t>(yy) * w + xx;
            if (valid[j] && std::fabs(static_cast<double>(d[j]) - zi) <= tol) ++consistent;
          }
        }
        if (consistent < p.flying_min_consistent_neighbors) drop[i] = 1;
      }
    }
    for (size_t i = 0; i < n; ++i)
      if (drop[i]) {
        valid[i] = 0;
        --count;
      }
  }
  mask->after_flying = count;
}

}  // namespace lingtouch
