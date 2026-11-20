#include "lingtouch/report_json.h"

#include <chrono>
#include <cstdio>
#include <cstring>

namespace lingtouch {
namespace {

std::string number(double v) {
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%.6g", v);
  return buf;
}

std::string number(uint64_t v) { return std::to_string(v); }

struct Fnv {
  uint64_t h = 1469598103934665603ULL;
  void bytes(const void* p, size_t n) {
    const unsigned char* b = static_cast<const unsigned char*>(p);
    for (size_t i = 0; i < n; ++i) {
      h ^= b[i];
      h *= 1099511628211ULL;
    }
  }
  void u32(uint32_t v) {
    const unsigned char b[4] = {static_cast<unsigned char>(v), static_cast<unsigned char>(v >> 8),
                                static_cast<unsigned char>(v >> 16), static_cast<unsigned char>(v >> 24)};
    bytes(b, 4);
  }
  void f64(double v) {
    uint64_t bits = 0;
    std::memcpy(&bits, &v, sizeof(bits));
    u32(static_cast<uint32_t>(bits));
    u32(static_cast<uint32_t>(bits >> 32));
  }
};

}  // namespace

int64_t monotonic_now_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

std::string json_escape(const std::string& s) {
  std::string out;
  out.reserve(s.size() + 2);
  for (unsigned char c : s) {
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      default:
        if (c < 0x20) {
          char buf[8];
          std::snprintf(buf, sizeof(buf), "\\u%04x", c);
          out += buf;
        } else {
          out += static_cast<char>(c);  // UTF-8 原样保留
        }
    }
  }
  return out;
}

std::string grid_digest(const OccupancyGrid& g) {
  Fnv f;
  f.u32(static_cast<uint32_t>(g.status));
  for (CellState c : g.cells) f.u32(static_cast<uint32_t>(c));
  for (const CellDiagnostics& d : g.diag) {
    f.u32(d.band_points);
    f.u32(d.ground_points);
    f.u32(d.other_points);
    f.u32(d.ground_subblocks_seen);
  }
  f.u32(g.counts.pixels);
  f.u32(g.counts.value_valid);
  f.u32(g.counts.after_wrap);
  f.u32(g.counts.after_flying);
  f.u32(g.counts.in_grid);
  f.u32(g.ground.ok ? 1 : 0);
  for (double v : g.ground.normal) f.f64(v);
  f.f64(g.ground.height_m);
  f.u32(g.ground.inliers);
  f.u32(g.ground.candidates);
  char buf[17];
  std::snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(f.h));
  return buf;
}

std::string grid_json(const OccupancyGrid& g, int64_t now_ns) {
  const bool has_frame = g.status != GridStatus::kNoFrame;
  std::string cells;
  for (CellState c : g.cells) cells += static_cast<char>('0' + static_cast<int>(c));
  std::string j = "{";
  j += "\"status\":\"" + std::string(grid_status_name(g.status)) + "\"";
  j += ",\"failure\":\"" + json_escape(g.ground.failure) + "\"";
  j += ",\"frame_id\":" + (has_frame ? number(g.source_frame_id) : std::string("null"));
  j += ",\"age_ms\":" + (has_frame ? number(static_cast<double>(now_ns - g.capture_time_ns) / 1e6) : std::string("null"));
  j += ",\"intrinsics_id\":\"" + json_escape(g.intrinsics_id) + "\"";
  j += ",\"digest\":\"" + grid_digest(g) + "\"";
  j += ",\"cells\":" + (has_frame ? "\"" + cells + "\"" : std::string("null"));
  j += ",\"ground\":{\"ok\":" + std::string(g.ground.ok ? "true" : "false");
  if (g.ground.ok) {
    j += ",\"height_m\":" + number(g.ground.height_m) + ",\"pitch_deg\":" + number(g.ground.pitch_deg) +
         ",\"roll_deg\":" + number(g.ground.roll_deg) + ",\"rms_m\":" + number(g.ground.rms_m);
  }
  j += ",\"inliers\":" + number(static_cast<uint64_t>(g.ground.inliers)) +
       ",\"candidates\":" + number(static_cast<uint64_t>(g.ground.candidates)) + "}";
  j += ",\"counts\":{\"pixels\":" + number(static_cast<uint64_t>(g.counts.pixels)) +
       ",\"value_valid\":" + number(static_cast<uint64_t>(g.counts.value_valid)) +
       ",\"after_wrap\":" + number(static_cast<uint64_t>(g.counts.after_wrap)) +
       ",\"after_flying\":" + number(static_cast<uint64_t>(g.counts.after_flying)) +
       ",\"in_grid\":" + number(static_cast<uint64_t>(g.counts.in_grid)) + "}";
  // 每格诊断：[高度带点数, 地面点数, 看到地面的小块数]
  j += ",\"diag\":[";
  for (int i = 0; i < kGridCells; ++i) {
    const CellDiagnostics& d = g.diag[i];
    if (i) j += ",";
    j += "[" + number(static_cast<uint64_t>(d.band_points)) + "," + number(static_cast<uint64_t>(d.ground_points)) +
         "," + number(static_cast<uint64_t>(d.ground_subblocks_seen)) + "]";
  }
  j += "]}";
  return j;
}

std::string stats_json(const EngineStats& s) {
  const AssemblerStats& a = s.assembler;
  return "{\"transfers\":" + number(s.transfers) + ",\"packets\":" + number(a.packets) +
         ",\"empty_packets\":" + number(a.empty_packets) + ",\"packet_errors\":" + number(a.packet_errors) +
         ",\"bad_header\":" + number(a.bad_header) + ",\"uvc_errors\":" + number(a.uvc_errors) +
         ",\"frames\":" + number(a.frames) + ",\"incomplete\":" + number(a.incomplete) +
         ",\"overflow\":" + number(a.overflow) + ",\"frames_processed\":" + number(s.frames_processed) +
         ",\"frames_dropped_busy\":" + number(s.frames_dropped_busy) +
         ",\"last_process_ms\":" + number(s.last_process_ms) + "}";
}

}  // namespace lingtouch
