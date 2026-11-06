// 端侧参数。唯一来源是 core/config/lingtouch_defaults.conf（编译时嵌入），
// 这里的结构体只是它的内存形式；默认值不在 C++ 里另写一份。
#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

#include "lingtouch/result.h"
#include "lingtouch/tactile.h"
#include "lingtouch/types.h"

namespace lingtouch {

struct DepthParams {
  DepthMeaning meaning = DepthMeaning::kOpticalAxisZ;
  bool undistort = false;
  bool image_mirrored = false;
  uint32_t min_valid_mm = 0;
  uint32_t max_valid_mm = 0;
  bool reject_value_one = false;
  int wrap_window_radius_px = 0;
  double wrap_invalid_fraction = 0;
  uint32_t wrap_max_depth_mm = 0;
  int flying_min_consistent_neighbors = 0;
  uint32_t flying_abs_tolerance_mm = 0;
  double flying_rel_tolerance = 0;
};

struct GroundParams {
  int sample_stride_px = 0;
  int ransac_iterations = 0;
  uint64_t ransac_seed = 0;
  double inlier_distance_m = 0;
  uint32_t min_inliers = 0;
  double camera_height_min_m = 0;
  double camera_height_max_m = 0;
  double max_tilt_deg = 0;
  double min_forward_span_m = 0;
  double below_margin_m = 0;
  double max_below_fraction = 0;
};

struct GridParams {
  double height_band_min_m = 0;
  double height_band_max_m = 0;
  double ground_tolerance_m = 0;
  uint32_t obstacle_min_points = 0;
  uint32_t free_max_band_points = 0;
  uint32_t free_min_ground_points_per_subblock = 0;
  int free_max_missing_subblocks = 0;
};

struct TactileParams {
  // 待 Hsinlung 定：没设定时为空，App 必须让使用者手选。
  std::optional<UnknownCellPolicy> unknown_cell_policy;
  bool mirror_left_right = false;
  bool module_rot180 = false;
};

struct Config {
  DepthParams depth;
  GroundParams ground;
  GridParams grid;
  TactileParams tactile;
};

// 嵌入的默认参数文本（core/config/lingtouch_defaults.conf 原文）。
std::string_view default_config_text();

// 解析默认参数；文本里每个键都必须出现。嵌入文本有误时返回错误（单元测试保证不会）。
Result<Config> default_config();

// 在 base 上应用一段"键 = 值"文本。未知键、格式错误都报错；require_all_keys 时缺键也报错。
Result<Config> parse_config(std::string_view text, const Config& base, bool require_all_keys);

// 按 lingtouch_defaults.conf 的键名输出当前参数（用于报告、界面和跨平台比对）。
std::string format_config(const Config& config);

}  // namespace lingtouch
