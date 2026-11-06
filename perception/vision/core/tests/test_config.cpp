#include <string>

#include "lingtouch/config.h"
#include "test_harness.h"

using namespace lingtouch;

LT_TEST(defaults_parse_and_cover_every_key) {
  Result<Config> c = default_config();
  LT_CHECK_MSG(c, c.error());
  if (!c) return;
  const Config& cfg = c.value();
  LT_CHECK(cfg.depth.meaning == DepthMeaning::kOpticalAxisZ);
  LT_CHECK(cfg.depth.min_valid_mm == 100);
  LT_CHECK(cfg.grid.height_band_min_m == 0.10);
  LT_CHECK(cfg.grid.height_band_max_m == 1.90);
  // 状态 2 的表示方式：待 Hsinlung 定，默认未设定
  LT_CHECK(!cfg.tactile.unknown_cell_policy.has_value());
  LT_CHECK(cfg.tactile.mirror_left_right);
  LT_CHECK(cfg.tactile.module_rot180);
  // 输出再读回应得到同样的参数
  Result<Config> again = parse_config(format_config(cfg), Config{}, true);
  LT_CHECK_MSG(again, again.error());
  if (again) LT_CHECK(format_config(again.value()) == format_config(cfg));
}

LT_TEST(overrides_and_errors) {
  const Config base = default_config().value();
  Result<Config> c = parse_config("tactile.unknown_cell_policy = raised\ndepth.meaning = radial  # 注释\n", base, false);
  LT_CHECK_MSG(c, c.error());
  if (c) {
    LT_CHECK(c.value().tactile.unknown_cell_policy == UnknownCellPolicy::kRaised);
    LT_CHECK(c.value().depth.meaning == DepthMeaning::kRadialDistance);
  }
  LT_CHECK(!parse_config("no.such.key = 1\n", base, false));
  LT_CHECK(!parse_config("grid.obstacle_min_points = abc\n", base, false));
  LT_CHECK(!parse_config("grid.obstacle_min_points =\n", base, false));  // 只有标明可留空的键能留空
  LT_CHECK(!parse_config("grid.height_band_min_m = 2.5\n", base, false));  // 下限大于上限
  LT_CHECK(!parse_config("depth.min_valid_mm = 100\ndepth.min_valid_mm = 100\n", base, false));  // 重复
  LT_CHECK(!parse_config("depth.meaning = optical_z\n", Config{}, true));  // 缺键
}

LT_TEST(number_parsing_ignores_locale_style_commas) {
  const Config base = default_config().value();
  LT_CHECK(!parse_config("grid.ground_tolerance_m = 0,05\n", base, false));
  Result<Config> c = parse_config("grid.ground_tolerance_m = 0.05\n", base, false);
  LT_CHECK(c && c.value().grid.ground_tolerance_m == 0.05);
}

LT_TEST_MAIN()
