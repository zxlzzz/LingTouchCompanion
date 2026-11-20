#include "lingtouch/config.h"

#include <charconv>
#include <cmath>
#include <functional>
#include <iomanip>
#include <locale>
#include <set>
#include <sstream>
#include <vector>

namespace lingtouch {
namespace {

#include "default_config.inc"  // 定义 kDefaultConfigText（由 CMake 从 lingtouch_defaults.conf 生成）

std::string_view trim(std::string_view s) {
  const char* ws = " \t\r\n";
  const size_t b = s.find_first_not_of(ws);
  if (b == std::string_view::npos) return {};
  const size_t e = s.find_last_not_of(ws);
  return s.substr(b, e - b + 1);
}

bool parse_double(std::string_view s, double& out) {
  std::istringstream is{std::string(s)};
  is.imbue(std::locale::classic());  // 与系统区域设置无关：小数点永远是 '.'
  double v = 0;
  is >> v;
  if (is.fail() || !is.eof() || !std::isfinite(v)) return false;
  out = v;
  return true;
}

template <typename T>
bool parse_integer(std::string_view s, T& out) {
  T v{};
  const auto res = std::from_chars(s.data(), s.data() + s.size(), v);
  if (res.ec != std::errc() || res.ptr != s.data() + s.size()) return false;
  out = v;
  return true;
}

bool parse_bool(std::string_view s, bool& out) {
  if (s == "true") {
    out = true;
    return true;
  }
  if (s == "false") {
    out = false;
    return true;
  }
  return false;
}

// 最短的、能原样读回的十进制写法，保证输出与平台无关。
std::string format_double(double v) {
  for (int precision = 1; precision <= 17; ++precision) {
    std::ostringstream os;
    os.imbue(std::locale::classic());
    os << std::setprecision(precision) << v;
    double back = 0;
    if (parse_double(os.str(), back) && back == v) return os.str();
  }
  std::ostringstream os;
  os.imbue(std::locale::classic());
  os << std::setprecision(17) << v;
  return os.str();
}

struct Key {
  const char* name;
  bool may_be_empty;
  // 返回空串表示成功，否则是错误说明
  std::function<std::string(Config&, std::string_view)> set;
  std::function<std::string(const Config&)> get;
};

template <typename Getter>
Key bool_key(const char* name, Getter field) {
  return Key{name, false,
             [field](Config& c, std::string_view v) -> std::string {
               return parse_bool(v, field(c)) ? "" : "应为 true 或 false";
             },
             [field](const Config& c) -> std::string {
               return field(const_cast<Config&>(c)) ? "true" : "false";
             }};
}

template <typename T, typename Getter>
Key int_key(const char* name, Getter field, T lo, T hi) {
  return Key{name, false,
             [field, lo, hi](Config& c, std::string_view v) -> std::string {
               T x{};
               if (!parse_integer(v, x)) return "应为整数";
               if (x < lo || x > hi) return "超出范围 [" + std::to_string(lo) + ", " + std::to_string(hi) + "]";
               field(c) = x;
               return "";
             },
             [field](const Config& c) -> std::string { return std::to_string(field(const_cast<Config&>(c))); }};
}

template <typename Getter>
Key double_key(const char* name, Getter field, double lo, double hi) {
  return Key{name, false,
             [field, lo, hi](Config& c, std::string_view v) -> std::string {
               double x = 0;
               if (!parse_double(v, x)) return "应为数字";
               if (x < lo || x > hi) return "超出范围 [" + format_double(lo) + ", " + format_double(hi) + "]";
               field(c) = x;
               return "";
             },
             [field](const Config& c) -> std::string { return format_double(field(const_cast<Config&>(c))); }};
}

const std::vector<Key>& keys() {
  static const std::vector<Key> k = {
      Key{"depth.meaning", false,
          [](Config& c, std::string_view v) -> std::string {
            if (v == "optical_z") c.depth.meaning = DepthMeaning::kOpticalAxisZ;
            else if (v == "radial") c.depth.meaning = DepthMeaning::kRadialDistance;
            else return "应为 optical_z 或 radial";
            return "";
          },
          [](const Config& c) -> std::string {
            return c.depth.meaning == DepthMeaning::kRadialDistance ? "radial" : "optical_z";
          }},
      bool_key("depth.undistort", [](Config& c) -> bool& { return c.depth.undistort; }),
      bool_key("depth.image_mirrored", [](Config& c) -> bool& { return c.depth.image_mirrored; }),
      int_key<uint32_t>("depth.min_valid_mm", [](Config& c) -> uint32_t& { return c.depth.min_valid_mm; }, 0, 65535),
      int_key<uint32_t>("depth.max_valid_mm", [](Config& c) -> uint32_t& { return c.depth.max_valid_mm; }, 1, 65535),
      bool_key("depth.reject_value_one", [](Config& c) -> bool& { return c.depth.reject_value_one; }),
      int_key<int>("depth.wrap_window_radius_px", [](Config& c) -> int& { return c.depth.wrap_window_radius_px; }, 0, 32),
      double_key("depth.wrap_invalid_fraction", [](Config& c) -> double& { return c.depth.wrap_invalid_fraction; }, 0.0, 1.0),
      int_key<uint32_t>("depth.wrap_max_depth_mm", [](Config& c) -> uint32_t& { return c.depth.wrap_max_depth_mm; }, 0, 65535),
      int_key<int>("depth.flying_min_consistent_neighbors",
                   [](Config& c) -> int& { return c.depth.flying_min_consistent_neighbors; }, 0, 8),
      int_key<uint32_t>("depth.flying_abs_tolerance_mm",
                        [](Config& c) -> uint32_t& { return c.depth.flying_abs_tolerance_mm; }, 0, 65535),
      double_key("depth.flying_rel_tolerance", [](Config& c) -> double& { return c.depth.flying_rel_tolerance; }, 0.0, 10.0),

      int_key<int>("ground.sample_stride_px", [](Config& c) -> int& { return c.ground.sample_stride_px; }, 1, 64),
      int_key<int>("ground.ransac_iterations", [](Config& c) -> int& { return c.ground.ransac_iterations; }, 1, 100000),
      int_key<uint64_t>("ground.ransac_seed", [](Config& c) -> uint64_t& { return c.ground.ransac_seed; }, 0,
                        UINT64_MAX),
      double_key("ground.inlier_distance_m", [](Config& c) -> double& { return c.ground.inlier_distance_m; }, 1e-4, 1.0),
      int_key<uint32_t>("ground.min_inliers", [](Config& c) -> uint32_t& { return c.ground.min_inliers; }, 3, 10000000),
      double_key("ground.camera_height_min_m", [](Config& c) -> double& { return c.ground.camera_height_min_m; }, 0.0, 10.0),
      double_key("ground.camera_height_max_m", [](Config& c) -> double& { return c.ground.camera_height_max_m; }, 0.0, 10.0),
      double_key("ground.max_tilt_deg", [](Config& c) -> double& { return c.ground.max_tilt_deg; }, 0.0, 89.0),
      double_key("ground.min_forward_span_m", [](Config& c) -> double& { return c.ground.min_forward_span_m; }, 0.0, 20.0),
      double_key("ground.below_margin_m", [](Config& c) -> double& { return c.ground.below_margin_m; }, 0.0, 5.0),
      double_key("ground.max_below_fraction", [](Config& c) -> double& { return c.ground.max_below_fraction; }, 0.0, 1.0),

      double_key("grid.height_band_min_m", [](Config& c) -> double& { return c.grid.height_band_min_m; }, 0.0, 5.0),
      double_key("grid.height_band_max_m", [](Config& c) -> double& { return c.grid.height_band_max_m; }, 0.0, 5.0),
      double_key("grid.ground_tolerance_m", [](Config& c) -> double& { return c.grid.ground_tolerance_m; }, 1e-4, 1.0),
      int_key<uint32_t>("grid.obstacle_min_points", [](Config& c) -> uint32_t& { return c.grid.obstacle_min_points; }, 1,
                        10000000),
      int_key<uint32_t>("grid.free_max_band_points", [](Config& c) -> uint32_t& { return c.grid.free_max_band_points; }, 0,
                        10000000),
      int_key<uint32_t>("grid.free_min_ground_points_per_subblock",
                        [](Config& c) -> uint32_t& { return c.grid.free_min_ground_points_per_subblock; }, 1, 10000000),
      int_key<int>("grid.free_max_missing_subblocks",
                   [](Config& c) -> int& { return c.grid.free_max_missing_subblocks; }, 0, kSubblocksPerCell),

      Key{"tactile.unknown_cell_policy", true,
          [](Config& c, std::string_view v) -> std::string {
            if (v.empty()) c.tactile.unknown_cell_policy.reset();
            else if (v == "flat") c.tactile.unknown_cell_policy = UnknownCellPolicy::kFlat;
            else if (v == "raised") c.tactile.unknown_cell_policy = UnknownCellPolicy::kRaised;
            else return "应为 flat、raised 或留空（待定）";
            return "";
          },
          [](const Config& c) -> std::string {
            return c.tactile.unknown_cell_policy ? unknown_policy_name(*c.tactile.unknown_cell_policy) : "";
          }},
      bool_key("tactile.mirror_left_right", [](Config& c) -> bool& { return c.tactile.mirror_left_right; }),
      bool_key("tactile.module_rot180", [](Config& c) -> bool& { return c.tactile.module_rot180; }),
  };
  return k;
}

std::string validate(const Config& c) {
  if (c.depth.min_valid_mm >= c.depth.max_valid_mm) return "depth.min_valid_mm 必须小于 depth.max_valid_mm";
  if (c.ground.camera_height_min_m >= c.ground.camera_height_max_m)
    return "ground.camera_height_min_m 必须小于 ground.camera_height_max_m";
  if (c.grid.height_band_min_m >= c.grid.height_band_max_m)
    return "grid.height_band_min_m 必须小于 grid.height_band_max_m";
  if (c.grid.ground_tolerance_m >= c.grid.height_band_min_m)
    return "grid.ground_tolerance_m 必须小于 grid.height_band_min_m（否则同一个点既算地面又算障碍）";
  return "";
}

}  // namespace

std::string_view default_config_text() { return kDefaultConfigText; }

Result<Config> default_config() { return parse_config(default_config_text(), Config{}, true); }

Result<Config> parse_config(std::string_view text, const Config& base, bool require_all_keys) {
  Config c = base;
  std::set<std::string> seen;
  size_t line_no = 0;
  size_t pos = 0;
  while (pos <= text.size()) {
    const size_t end = text.find('\n', pos);
    std::string_view line = text.substr(pos, end == std::string_view::npos ? std::string_view::npos : end - pos);
    pos = end == std::string_view::npos ? text.size() + 1 : end + 1;
    ++line_no;
    const size_t hash = line.find('#');
    if (hash != std::string_view::npos) line = line.substr(0, hash);
    line = trim(line);
    if (line.empty()) continue;
    const size_t eq = line.find('=');
    const std::string where = "第 " + std::to_string(line_no) + " 行：";
    if (eq == std::string_view::npos) return Result<Config>::failure(where + "缺少 '='");
    const std::string name(trim(line.substr(0, eq)));
    const std::string_view value = trim(line.substr(eq + 1));
    const Key* key = nullptr;
    for (const Key& k : keys())
      if (name == k.name) key = &k;
    if (key == nullptr) return Result<Config>::failure(where + "未知的键 " + name);
    if (!seen.insert(name).second) return Result<Config>::failure(where + name + " 重复出现");
    if (value.empty() && !key->may_be_empty) return Result<Config>::failure(where + name + " 不能留空");
    const std::string err = key->set(c, value);
    if (!err.empty()) return Result<Config>::failure(where + name + " " + err);
  }
  if (require_all_keys) {
    for (const Key& k : keys())
      if (!seen.count(k.name)) return Result<Config>::failure(std::string("缺少键 ") + k.name);
  }
  const std::string err = validate(c);
  if (!err.empty()) return Result<Config>::failure(err);
  return Result<Config>::success(c);
}

std::string format_config(const Config& config) {
  std::string out;
  for (const Key& k : keys()) {
    out += k.name;
    out += " = ";
    out += k.get(config);
    out += '\n';
  }
  return out;
}

}  // namespace lingtouch
