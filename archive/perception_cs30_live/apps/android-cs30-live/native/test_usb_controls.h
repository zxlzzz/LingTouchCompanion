#pragma once
#include <string>
#include <cstddef>
bool mock_java_claim(int id, bool force);
bool mock_java_release(int id);
std::string mock_policy_report();
std::string run_transport_regressions(const unsigned char* blob, size_t size);
