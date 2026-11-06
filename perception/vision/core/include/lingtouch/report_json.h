// 把栅格和统计转成 JSON 文本，安卓（JNI）和鸿蒙（Node-API）共用，两边界面拿到的字段一致。
#pragma once

#include <cstdint>
#include <string>

#include "lingtouch/engine.h"
#include "lingtouch/types.h"

namespace lingtouch {

// cells：54 个字符 '0'/'1'/'2'，row 0（最远）在前；没有帧时 status 为 "no_frame"，其余字段为空值。
std::string grid_json(const OccupancyGrid& grid, int64_t now_ns);
std::string stats_json(const EngineStats& stats);
std::string json_escape(const std::string& s);

// 栅格结果的摘要（FNV-1a 64，覆盖状态、54 格、每格诊断、各阶段计数、地面法线与高度的二进制位）。
// 两个平台对同一帧、同一参数、同一内参算出的摘要应完全相同（docs/device_tests.md 第 3 条）。
std::string grid_digest(const OccupancyGrid& grid);

int64_t monotonic_now_ns();

}  // namespace lingtouch
