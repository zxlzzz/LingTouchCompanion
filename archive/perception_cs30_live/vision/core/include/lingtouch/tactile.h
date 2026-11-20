// 点阵编码：本次只实现旧板（V2.8 固件）协议。
//
// 旧板：BLE 服务 FFE0，写 FFE1 下发 15 字节，每字节低 6 位对应一个六点模组；
// FFE3 通知 0x01 = 刷新完成，0x04 = 按键扫描请求。逻辑栅格 10 行 × 9 列，
// 位映射以 experiments/chi2027/visionss/frame_converter.py（硬件验证过）为准。
// 新板（9+1 个模组）等固件定了再加一个编码器，其余模块不动。
#pragma once

#include <array>
#include <cstdint>

#include "lingtouch/result.h"
#include "lingtouch/types.h"

namespace lingtouch {

constexpr int kLegacyRows = 10;
constexpr int kLegacyCols = 9;
constexpr int kLegacyDots = kLegacyRows * kLegacyCols;
constexpr int kLegacyModules = 15;
constexpr int kLegacyFrameBytes = 15;

// 旧板 BLE 协议常量（hardware/firmware/braille_15module_prod）
constexpr const char* kLegacyServiceUuid = "0000FFE0-0000-1000-8000-00805F9B34FB";
constexpr const char* kLegacyFrameCharUuid = "0000FFE1-0000-1000-8000-00805F9B34FB";
constexpr const char* kLegacyStatusCharUuid = "0000FFE3-0000-1000-8000-00805F9B34FB";
constexpr uint8_t kLegacyEventRefreshDone = 0x01;
constexpr uint8_t kLegacyEventScanRequest = 0x04;

// 状态 2（未知）在触点上表示为平还是凸：待 Hsinlung 定。
// 编码函数必须显式传入，没有默认值；数值 0 不合法，防止被零初始化"悄悄"选中一种。
enum class UnknownCellPolicy : uint8_t { kFlat = 1, kRaised = 2 };

const char* unknown_policy_name(UnknownCellPolicy policy);
bool is_valid_policy(UnknownCellPolicy policy);

// 旧板逻辑栅格，row 0 最远，1 = 凸起。
using LegacyDotGrid = std::array<uint8_t, kLegacyDots>;
using LegacyFrame = std::array<uint8_t, kLegacyFrameBytes>;

// 与 frame_converter.grid_to_bytes 逐字节一致（不做镜像）。
// module_rot180 对应 frame_converter.MODULE_ROT180（真机为 true）。
LegacyFrame legacy_grid_to_bytes(const LegacyDotGrid& grid, bool module_rot180);
LegacyDotGrid legacy_bytes_to_grid(const LegacyFrame& frame, bool module_rot180);

// 与 frame_converter.mirror_grid_horizontal 一致：每行左右翻转。
LegacyDotGrid mirror_legacy_grid(const LegacyDotGrid& grid);

// 9×6 放进旧板 10×9 的最近 6 行（两者都从 1.0 m 起、每格 40 cm）：
// 新 row r → 旧 row r+4；旧 row 0–3 全平。1 → 凸，0 → 平，2 → 按 policy。
Result<LegacyDotGrid> place_on_legacy_board(const std::array<CellState, kGridCells>& cells,
                                            UnknownCellPolicy policy);

// 两个装配相关的开关都必须显式给出（配置 tactile.mirror_left_right / tactile.module_rot180）。
struct LegacyBoardLayout {
  bool mirror_left_right;
  bool module_rot180;
};

// 9×6 → 15 字节：放进旧板栅格 → （可选）左右镜像 → grid_to_bytes。
Result<LegacyFrame> encode_legacy_frame(const std::array<CellState, kGridCells>& cells,
                                        UnknownCellPolicy policy, const LegacyBoardLayout& layout);

}  // namespace lingtouch
