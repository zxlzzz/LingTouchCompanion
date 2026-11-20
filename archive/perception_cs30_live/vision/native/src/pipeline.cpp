#include "lingtouch/perception/pipeline.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

#include "lingtouch/perception/ground_fit.h"

namespace lingtouch {

DepthPipeline::DepthPipeline(const Config& config) : config_(config), builder_(config.grid) {}

Status DepthPipeline::set_intrinsics(const CameraIntrinsics& intrinsics) {
  Result<DepthCameraModel> m = DepthCameraModel::create(intrinsics, config_.depth.undistort);
  if (!m) return Status::failure(m.error());
  model_ = std::move(m.value());
  return Status::success();
}

OccupancyGrid DepthPipeline::process(const DepthFrame& frame) {
  OccupancyGrid g;
  g.source_frame_id = frame.frame_id;
  g.capture_time_ns = frame.capture_time_ns;
  if (!model_) {
    g.status = GridStatus::kNoCalibration;
    g.ground.failure = "没有可用内参";
    return g;
  }
  const DepthCameraModel& m = *model_;
  g.intrinsics_id = m.intrinsics().id;
  const size_t n = static_cast<size_t>(m.width()) * static_cast<size_t>(m.height());
  if (frame.width != m.width() || frame.height != m.height() || frame.depth_mm.size() != n) {
    g.status = GridStatus::kNoCalibration;
    char buf[160];
    std::snprintf(buf, sizeof(buf), "帧尺寸 %dx%d 与内参 %dx%d 不符", frame.width, frame.height, m.width(), m.height());
    g.ground.failure = buf;
    return g;
  }
  g.counts.pixels = static_cast<uint32_t>(n);

  compute_depth_mask(frame, m, config_.depth, &mask_);
  g.counts.value_valid = mask_.value_valid;
  g.counts.after_wrap = mask_.after_wrap;
  g.counts.after_flying = mask_.after_flying;

  points_.clear();
  candidates_.clear();
  const int stride = config_.ground.sample_stride_px;
  const DepthMeaning meaning = config_.depth.meaning;
  for (int v = 0; v < m.height(); ++v) {
    for (int u = 0; u < m.width(); ++u) {
      const size_t i = static_cast<size_t>(v) * static_cast<size_t>(m.width()) + static_cast<size_t>(u);
      if (!mask_.valid[i]) continue;
      const Point3 p = backproject(m, i, frame.depth_mm[i], meaning);
      points_.push_back(p);
      if (u % stride == 0 && v % stride == 0) candidates_.push_back(p);
    }
  }

  g.ground = fit_ground_plane(candidates_, config_.ground);
  if (!g.ground.ok) {
    g.status = GridStatus::kGroundFitFailed;  // 降级：整张图为 2（cells 默认就是 kUnknown）
    return g;
  }
  const GroundFrame gf = make_ground_frame(g.ground, config_.depth.image_mirrored);
  ground_points_.clear();
  ground_points_.reserve(points_.size());
  for (const Point3& p : points_) ground_points_.push_back(gf.to_ground(p));
  builder_.build(ground_points_, &g);
  g.status = GridStatus::kOk;
  return g;
}

PlaneCheckReport check_planarity(const DepthFrame& frame, const CameraIntrinsics& intrinsics, const DepthParams& depth,
                                 double roi_fraction) {
  PlaneCheckReport report;
  report.roi_fraction = roi_fraction;
  const int w = frame.width;
  const int h = frame.height;
  const int u0 = static_cast<int>(w * (1.0 - roi_fraction) / 2.0);
  const int u1 = w - u0;
  const int v0 = static_cast<int>(h * (1.0 - roi_fraction) / 2.0);
  const int v1 = h - v0;
  const DepthMeaning meanings[2] = {DepthMeaning::kOpticalAxisZ, DepthMeaning::kRadialDistance};
  const bool undistorts[2] = {true, false};
  for (DepthMeaning meaning : meanings) {
    for (bool undistort : undistorts) {
      PlaneHypothesis hyp;
      hyp.meaning = meaning;
      hyp.undistort = undistort;
      Result<DepthCameraModel> model = DepthCameraModel::create(intrinsics, undistort);
      if (!model) {
        hyp.failure = model.error();
        report.hypotheses.push_back(hyp);
        continue;
      }
      if (frame.width != intrinsics.width || frame.height != intrinsics.height) {
        hyp.failure = "帧尺寸与内参不符";
        report.hypotheses.push_back(hyp);
        continue;
      }
      DepthMask mask;
      compute_depth_mask(frame, model.value(), depth, &mask);
      std::vector<Point3> pts;
      for (int v = v0; v < v1; ++v) {
        for (int u = u0; u < u1; ++u) {
          const size_t i = static_cast<size_t>(v) * static_cast<size_t>(w) + static_cast<size_t>(u);
          if (mask.valid[i]) pts.push_back(backproject(model.value(), i, frame.depth_mm[i], meaning));
        }
      }
      hyp.points = static_cast<uint32_t>(pts.size());
      std::array<double, 3> normal{};
      double offset = 0;
      if (pts.size() < 100 || !fit_plane_least_squares(pts, &normal, &offset)) {
        hyp.failure = "中央区域有效点太少（需要至少 100 个）";
        report.hypotheses.push_back(hyp);
        continue;
      }
      std::vector<double> residual(pts.size());
      double sum_sq = 0;
      for (size_t k = 0; k < pts.size(); ++k) {
        const double r = std::fabs(normal[0] * pts[k].x + normal[1] * pts[k].y + normal[2] * pts[k].z + offset);
        residual[k] = r;
        sum_sq += r * r;
      }
      const size_t idx95 = (residual.size() * 95) / 100;
      std::nth_element(residual.begin(), residual.begin() + static_cast<std::ptrdiff_t>(idx95), residual.end());
      hyp.ok = true;
      hyp.rms_mm = std::sqrt(sum_sq / static_cast<double>(pts.size())) * 1000.0;
      hyp.p95_mm = residual[idx95] * 1000.0;
      hyp.distance_m = std::fabs(offset);
      report.hypotheses.push_back(hyp);
    }
  }
  std::stable_sort(report.hypotheses.begin(), report.hypotheses.end(),
                   [](const PlaneHypothesis& a, const PlaneHypothesis& b) {
                     if (a.ok != b.ok) return a.ok;
                     return a.rms_mm < b.rms_mm;
                   });
  return report;
}

std::string format_plane_check(const PlaneCheckReport& report) {
  std::string out;
  char buf[256];
  std::snprintf(buf, sizeof(buf), "平面检查（图像中央 %.0f%%×%.0f%% 区域，残差越小越可能是对的假设）\n",
                report.roi_fraction * 100, report.roi_fraction * 100);
  out += buf;
  for (const PlaneHypothesis& h : report.hypotheses) {
    const char* meaning = h.meaning == DepthMeaning::kRadialDistance ? "radial" : "optical_z";
    if (h.ok) {
      std::snprintf(buf, sizeof(buf), "  %-9s %-6s rms %7.2f mm  p95 %7.2f mm  点数 %6u  距离 %.3f m\n", meaning,
                    h.undistort ? "去畸变" : "不去", h.rms_mm, h.p95_mm, h.points, h.distance_m);
    } else {
      std::snprintf(buf, sizeof(buf), "  %-9s %-6s 失败：%s\n", meaning, h.undistort ? "去畸变" : "不去",
                    h.failure.c_str());
    }
    out += buf;
  }
  return out;
}

std::string format_grid(const OccupancyGrid& grid) {
  std::string out;
  for (int row = 0; row < kGridRows; ++row) {
    for (int col = 0; col < kGridCols; ++col) out += static_cast<char>('0' + static_cast<int>(grid.cells[cell_index(row, col)]));
    out += '\n';
  }
  return out;
}

}  // namespace lingtouch
