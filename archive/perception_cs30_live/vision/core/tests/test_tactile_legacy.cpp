// 旧板编码器与 experiments/chi2027/visionss/frame_converter.py 逐字节对比。
// 向量由 core/tools/gen_legacy_vectors.py 用 frame_converter.py 生成（core/tests/data/legacy_vectors.txt）。
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

#include "lingtouch/tactile.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

std::string hex(const LegacyFrame& f) {
  std::string s;
  char buf[3];
  for (uint8_t b : f) {
    std::snprintf(buf, sizeof(buf), "%02x", b);
    s += buf;
  }
  return s;
}

int popcount(uint8_t b) {
  int n = 0;
  for (; b != 0; b = static_cast<uint8_t>(b & (b - 1))) ++n;
  return n;
}

std::array<CellState, kGridCells> parse_cells(const std::string& s) {
  std::array<CellState, kGridCells> cells{};
  for (int i = 0; i < kGridCells; ++i) cells[i] = static_cast<CellState>(s[i] - '0');
  return cells;
}

}  // namespace

LT_TEST(legacy_vectors_match_frame_converter) {
  std::ifstream in(LINGTOUCH_SOURCE_ROOT "/core/tests/data/legacy_vectors.txt");
  LT_CHECK_MSG(in.good(), "找不到 legacy_vectors.txt");
  std::string line;
  int grid_vectors = 0, chain_vectors = 0, mismatches = 0;
  while (std::getline(in, line)) {
    if (line.empty() || line[0] == '#') continue;
    std::istringstream ls(line);
    std::string kind;
    ls >> kind;
    if (kind == "grid") {
      int rot = 0;
      std::string bits, expected;
      ls >> rot >> bits >> expected;
      LegacyDotGrid g{};
      for (int i = 0; i < kLegacyDots; ++i) g[i] = static_cast<uint8_t>(bits[i] - '0');
      const LegacyFrame f = legacy_grid_to_bytes(g, rot != 0);
      if (hex(f) != expected) {
        if (++mismatches <= 5) std::printf("  grid 不一致：%s\n", line.c_str());
      }
      // 反向解码应还原
      if (legacy_bytes_to_grid(f, rot != 0) != g) ++mismatches;
      ++grid_vectors;
    } else if (kind == "chain") {
      int rot = 0, mirror = 0;
      std::string policy, cells, expected;
      ls >> rot >> mirror >> policy >> cells >> expected;
      const UnknownCellPolicy p = policy == "raised" ? UnknownCellPolicy::kRaised : UnknownCellPolicy::kFlat;
      Result<LegacyFrame> f = encode_legacy_frame(parse_cells(cells), p, LegacyBoardLayout{mirror != 0, rot != 0});
      if (!f || hex(f.value()) != expected) {
        if (++mismatches <= 5) std::printf("  chain 不一致：%s\n", line.c_str());
      }
      ++chain_vectors;
    }
  }
  std::printf("  %d 条 grid 向量、%d 条 chain 向量，不一致 %d 条\n", grid_vectors, chain_vectors, mismatches);
  LT_CHECK(grid_vectors >= 500);
  LT_CHECK(chain_vectors >= 800);
  LT_CHECK(mismatches == 0);
}

// 与 frame_converter._self_test 的两条断言相同
LT_TEST(rot180_corner_bits) {
  LegacyDotGrid g{};
  g[0] = 1;  // 左上角
  LT_CHECK(legacy_grid_to_bytes(g, true)[0] == 0x08);
  g = LegacyDotGrid{};
  g[kLegacyDots - 1] = 1;  // 右下角
  LT_CHECK(legacy_grid_to_bytes(g, true)[14] == 0x04);
}

LT_TEST(policy_must_be_explicit) {
  std::array<CellState, kGridCells> cells;
  cells.fill(CellState::kUnknown);
  const UnknownCellPolicy unset = static_cast<UnknownCellPolicy>(0);  // 零初始化得到的值
  LT_CHECK(!encode_legacy_frame(cells, unset, LegacyBoardLayout{true, true}));
  Result<LegacyFrame> flat = encode_legacy_frame(cells, UnknownCellPolicy::kFlat, LegacyBoardLayout{true, true});
  Result<LegacyFrame> raised = encode_legacy_frame(cells, UnknownCellPolicy::kRaised, LegacyBoardLayout{true, true});
  LT_CHECK(flat && raised);
  // 全 2 + 平 → 全平；全 2 + 凸 → 最近 6 行全凸、远处 4 行仍平
  int flat_bits = 0, raised_bits = 0;
  for (uint8_t b : flat.value()) flat_bits += popcount(b);
  for (uint8_t b : raised.value()) raised_bits += popcount(b);
  LT_CHECK(flat_bits == 0);
  LT_CHECK(raised_bits == kGridCells);
}

LT_TEST(far_four_rows_stay_flat) {
  std::array<CellState, kGridCells> cells;
  cells.fill(CellState::kOccupied);
  Result<LegacyDotGrid> placed = place_on_legacy_board(cells, UnknownCellPolicy::kFlat);
  LT_CHECK(placed);
  for (int r = 0; r < kLegacyRows; ++r)
    for (int c = 0; c < kLegacyCols; ++c) LT_CHECK(placed.value()[r * kLegacyCols + c] == (r >= 4 ? 1 : 0));
}

LT_TEST_MAIN()
