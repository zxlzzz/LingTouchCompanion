#pragma once
#include <cstdint>
#include <string>
#include <vector>
namespace mock_usb {
struct Packet { std::vector<uint8_t> bytes; int status = 0; };
void configure(std::vector<uint8_t> calibration, std::string fault);
void enqueue(const std::vector<uint8_t>& raw, int fid, const std::string& fault = "");
void disconnect();
std::string report_json();
bool clean();
}
