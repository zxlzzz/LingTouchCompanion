#include "lingtouch/perception/occupancy.h"

#include <cmath>

namespace lingtouch {
namespace {
constexpr int kSubCols = kGridCols * kSubblocksPerSide;  // 36 个 10 cm 小块（横向）
constexpr int kSubRows = kGridRows * kSubblocksPerSide;  // 24 个（前向）
}  // namespace

void OccupancyGridBuilder::build(const std::vector<GroundPoint>& points, OccupancyGrid* grid) {
  ground_hits_.assign(static_cast<size_t>(kSubCols) * kSubRows, 0);
  for (CellDiagnostics& d : grid->diag) d = CellDiagnostics{};
  uint32_t in_grid = 0;
  grid->evidence = SubcellEvidence{};

  for (const GroundPoint& p : points) {
    // 先按 10 cm 小块取整，再由小块推出格子，保证格子和小块的归属一致
    const double gx = std::floor((p.x - kGridXMinM) / kSubblockSizeM);
    const double gy = std::floor((p.y - kGridYMinM) / kSubblockSizeM);
    if (!(gx >= 0 && gx < kSubCols && gy >= 0 && gy < kSubRows)) continue;
    const int sx = static_cast<int>(gx);
    const int sy = static_cast<int>(gy);
    const int col = sx / kSubblocksPerSide;
    const int row = kGridRows - 1 - sy / kSubblocksPerSide;  // row 0 最远
    CellDiagnostics& d = grid->diag[cell_index(row, col)];
    ++in_grid;
    if (p.z >= params_.height_band_min_m && p.z <= params_.height_band_max_m) {
      ++d.band_points;
      grid->evidence.fine[sy * kSubCols + sx] = 1;
    } else if (std::fabs(p.z) <= params_.ground_tolerance_m) {
      ++d.ground_points;
      auto& fine = grid->evidence.fine[sy * kSubCols + sx];
      if (fine != 1) fine = 2;
      ++ground_hits_[static_cast<size_t>(sy) * kSubCols + sx];
    } else {
      ++d.other_points;
    }
  }
  grid->counts.in_grid = in_grid;
  grid->evidence.unknown.fill(0);
  for (int sy = 0; sy < kSubRows; ++sy) {
    for (int sx = 0; sx < kSubCols; ++sx) {
      const int cell = (kGridRows - 1 - sy / 4) * kGridCols + sx / 4;
      const auto state = grid->evidence.fine[sy * kSubCols + sx];
      if (state == 1) ++grid->evidence.obstacle[cell];
      else if (state == 2) ++grid->evidence.ground[cell];
      else ++grid->evidence.unknown[cell];
    }
  }

  for (int row = 0; row < kGridRows; ++row) {
    for (int col = 0; col < kGridCols; ++col) {
      const int idx = cell_index(row, col);
      CellDiagnostics& d = grid->diag[idx];
      const int sy0 = (kGridRows - 1 - row) * kSubblocksPerSide;
      const int sx0 = col * kSubblocksPerSide;
      int seen = 0;
      for (int j = 0; j < kSubblocksPerSide; ++j)
        for (int i = 0; i < kSubblocksPerSide; ++i)
          if (ground_hits_[static_cast<size_t>(sy0 + j) * kSubCols + (sx0 + i)] >=
              params_.free_min_ground_points_per_subblock)
            ++seen;
      d.ground_subblocks_seen = static_cast<uint8_t>(seen);
      CellState s = CellState::kUnknown;
      if (d.band_points >= params_.obstacle_min_points) {
        s = CellState::kOccupied;
      } else if (d.band_points <= params_.free_max_band_points &&
                 seen >= kSubblocksPerCell - params_.free_max_missing_subblocks) {
        s = CellState::kFree;
      }
      grid->cells[idx] = s;
    }
  }
}

}  // namespace lingtouch
