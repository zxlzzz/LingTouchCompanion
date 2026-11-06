// 9×6 栅格与 0/1/2（规则见 docs/plans/视觉方案审阅意见要点_Claude.md）：
//   1：高度带内实测点达到门槛（1 优先于 0）；
//   0：格内 4×4 个 10 cm 小块都有地面点，且高度带内没有点（允许缺几个小块由参数定）；
//   2：其余一律（看不到、被挡、视野外、无效）。
// 被挡住的地面没有点，视野外的格子没有点，所以它们自然是 2，不需要另外做射线遍历。
#pragma once

#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/modules.h"
#include "lingtouch/types.h"

namespace lingtouch {

class OccupancyGridBuilder final : public GeometryGrid {
 public:
  explicit OccupancyGridBuilder(GridParams params) : params_(params) {}
  void build(const std::vector<GroundPoint>& points, OccupancyGrid* grid) override;

 private:
  GridParams params_;
  std::vector<uint32_t> ground_hits_;  // 每个 10 cm 小块的地面点数
};

}  // namespace lingtouch
