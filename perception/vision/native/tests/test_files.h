// 测试读仓库里的数据文件（perception/cs30/ 下的标定 blob 和参考帧）。
#pragma once

#include <cstdint>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "lingtouch/types.h"

namespace lt_files {

inline std::vector<uint8_t> read_abs(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  return std::vector<uint8_t>(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

inline std::vector<uint8_t> read(const std::string& relative) {
  // Original cs30 evidence lists repository-relative paths. Accept those
  // unchanged while resolving within this self-contained perception module.
  const std::string local = relative.rfind("perception/", 0) == 0 ? relative.substr(11) : relative;
  return read_abs(std::string(LINGTOUCH_SOURCE_ROOT) + "/" + local);
}

// perception/cs30/reference_*.bin：640×480 uint16 小端毫米
inline lingtouch::DepthFrame read_depth_frame(const std::string& relative, uint64_t frame_id) {
  const std::vector<uint8_t> raw = read(relative);
  lingtouch::DepthFrame f;
  f.frame_id = frame_id;
  f.width = 640;
  f.height = 480;
  f.depth_mm.resize(raw.size() / 2);
  for (size_t i = 0; i < f.depth_mm.size(); ++i)
    f.depth_mm[i] = static_cast<uint16_t>(raw[2 * i] | (raw[2 * i + 1] << 8));
  return f;
}

}  // namespace lt_files
