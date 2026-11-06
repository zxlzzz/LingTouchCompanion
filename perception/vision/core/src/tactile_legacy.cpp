#include "lingtouch/tactile.h"

#include <string>

namespace lingtouch {
namespace {

struct BitPos {
  int bit;
  int dr;
  int dc;
};

// 照抄 frame_converter.py 的 _BIT_MAP_ROT180（硬件验证过），不要重新"猜"。
constexpr BitPos kBitMapRot180[6] = {{0, 1, 0}, {1, 1, 1}, {2, 1, 2}, {3, 0, 0}, {4, 0, 1}, {5, 0, 2}};

// _BIT_MAP_PROD = [(bit, 1 - dr, 2 - dc) for bit, dr, dc in _BIT_MAP_ROT180]
BitPos prod_from_rot180(const BitPos& p) { return BitPos{p.bit, 1 - p.dr, 2 - p.dc}; }

BitPos bit_pos(int i, bool module_rot180) {
  return module_rot180 ? kBitMapRot180[i] : prod_from_rot180(kBitMapRot180[i]);
}

}  // namespace

const char* unknown_policy_name(UnknownCellPolicy policy) {
  switch (policy) {
    case UnknownCellPolicy::kFlat:
      return "flat";
    case UnknownCellPolicy::kRaised:
      return "raised";
  }
  return "invalid";
}

bool is_valid_policy(UnknownCellPolicy policy) {
  return policy == UnknownCellPolicy::kFlat || policy == UnknownCellPolicy::kRaised;
}

LegacyFrame legacy_grid_to_bytes(const LegacyDotGrid& grid, bool module_rot180) {
  LegacyFrame out{};
  for (int m = 0; m < kLegacyModules; ++m) {
    const int r = (m / 3) * 2;
    const int c = (m % 3) * 3;
    uint8_t b = 0;
    for (int i = 0; i < 6; ++i) {
      const BitPos p = bit_pos(i, module_rot180);
      if (grid[(r + p.dr) * kLegacyCols + (c + p.dc)] != 0) b = static_cast<uint8_t>(b | (1u << p.bit));
    }
    out[m] = b;
  }
  return out;
}

LegacyDotGrid legacy_bytes_to_grid(const LegacyFrame& frame, bool module_rot180) {
  LegacyDotGrid g{};
  for (int m = 0; m < kLegacyModules; ++m) {
    const int r = (m / 3) * 2;
    const int c = (m % 3) * 3;
    for (int i = 0; i < 6; ++i) {
      const BitPos p = bit_pos(i, module_rot180);
      if (frame[m] & (1u << p.bit)) g[(r + p.dr) * kLegacyCols + (c + p.dc)] = 1;
    }
  }
  return g;
}

LegacyDotGrid mirror_legacy_grid(const LegacyDotGrid& grid) {
  LegacyDotGrid out{};
  for (int r = 0; r < kLegacyRows; ++r)
    for (int c = 0; c < kLegacyCols; ++c) out[r * kLegacyCols + c] = grid[r * kLegacyCols + (kLegacyCols - 1 - c)];
  return out;
}

Result<LegacyDotGrid> place_on_legacy_board(const std::array<CellState, kGridCells>& cells,
                                            UnknownCellPolicy policy) {
  if (!is_valid_policy(policy)) {
    return Result<LegacyDotGrid>::failure("状态 2 的表示方式未设定（必须显式选择 flat 或 raised）");
  }
  constexpr int kRowOffset = kLegacyRows - kGridRows;  // 9×6 占旧板最近的 6 行
  static_assert(kGridCols == kLegacyCols, "9 列与旧板 9 列一一对应");
  LegacyDotGrid g{};
  for (int r = 0; r < kGridRows; ++r) {
    for (int c = 0; c < kGridCols; ++c) {
      uint8_t v = 0;
      switch (cells[cell_index(r, c)]) {
        case CellState::kOccupied:
          v = 1;
          break;
        case CellState::kFree:
          v = 0;
          break;
        case CellState::kUnknown:
          v = policy == UnknownCellPolicy::kRaised ? 1 : 0;
          break;
        default:
          return Result<LegacyDotGrid>::failure("栅格里有非法的格子状态");
      }
      g[(r + kRowOffset) * kLegacyCols + c] = v;
    }
  }
  return Result<LegacyDotGrid>::success(g);
}

Result<LegacyFrame> encode_legacy_frame(const std::array<CellState, kGridCells>& cells,
                                        UnknownCellPolicy policy, const LegacyBoardLayout& layout) {
  Result<LegacyDotGrid> placed = place_on_legacy_board(cells, policy);
  if (!placed) return Result<LegacyFrame>::failure(placed.error());
  const LegacyDotGrid g = layout.mirror_left_right ? mirror_legacy_grid(placed.value()) : placed.value();
  return Result<LegacyFrame>::success(legacy_grid_to_bytes(g, layout.module_rot180));
}

}  // namespace lingtouch
