#pragma once
#include "lingtouch/types.h"
#include "lingtouch/result.h"
namespace depth_sim {
lingtouch::Result<std::string> binary_json(const std::array<uint8_t,54>& counts, int k);
std::string evidence_json(const lingtouch::OccupancyGrid& grid, bool connected = true);
}
