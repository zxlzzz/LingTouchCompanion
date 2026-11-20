// 标定 blob 无 schema 解码。期望值来自对 perception/cs30/calibration_*.bin 的逐字节解读（推断，非厂家文档）。
#include <cmath>

#include "lingtouch/perception/cs30_calibration.h"
#include "test_files.h"
#include "test_harness.h"

using namespace lingtouch;

LT_TEST(decode_640x480_depth_intrinsics) {
  const auto blob = lt_files::read("cs30/calibration_0.bin");
  Result<cs30::Calibration> c = cs30::decode_calibration(blob.data(), blob.size());
  LT_CHECK_MSG(c, c.error());
  if (!c) return;
  const CameraIntrinsics& d = c.value().depth;
  LT_CHECK(d.width == 640 && d.height == 480);
  LT_CHECK_NEAR(d.fx, 364.875, 1e-3);
  LT_CHECK_NEAR(d.fy, 364.778, 1e-3);
  LT_CHECK_NEAR(d.cx, 324.416, 1e-3);
  LT_CHECK_NEAR(d.cy, 231.051, 1e-3);
  LT_CHECK_NEAR(d.k1, -0.316446, 1e-6);
  LT_CHECK_NEAR(d.k2, 0.140359, 1e-6);
  LT_CHECK_NEAR(d.p1, -0.000302, 1e-6);
  LT_CHECK_NEAR(d.p2, -0.000482, 1e-6);
  LT_CHECK_NEAR(d.k3, -0.034901, 1e-6);
  LT_CHECK(d.inferred);
  LT_CHECK(c.value().serial == "HV0130315L0294");
  LT_CHECK(d.id.find("HV0130315L0294") != std::string::npos && d.id.find("640x480") != std::string::npos);
  LT_CHECK(c.value().has_rgb);
  LT_CHECK_NEAR(c.value().rgb.fx, 931.03, 0.01);
  LT_CHECK_NEAR(c.value().rgb_from_depth_translation[0], -43.895, 0.001);
  std::printf("  深度内参 %s：fx %.3f fy %.3f cx %.3f cy %.3f\n", d.id.c_str(), d.fx, d.fy, d.cx, d.cy);
}

LT_TEST(second_blob_is_half_resolution) {
  const auto b0 = lt_files::read("cs30/calibration_0.bin");
  const auto b1 = lt_files::read("cs30/calibration_1.bin");
  Result<cs30::Calibration> c0 = cs30::decode_calibration(b0.data(), b0.size());
  Result<cs30::Calibration> c1 = cs30::decode_calibration(b1.data(), b1.size());
  LT_CHECK(c0 && c1);
  if (!c0 || !c1) return;
  LT_CHECK(c1.value().depth.width == 320 && c1.value().depth.height == 240);
  // 只差浮点指数：恰好一半
  LT_CHECK(c1.value().depth.fx * 2 == c0.value().depth.fx);
  LT_CHECK(c1.value().depth.cy * 2 == c0.value().depth.cy);
  LT_CHECK(c1.value().depth.k1 == c0.value().depth.k1);
  int differing = 0;
  for (size_t i = 0; i < b0.size(); ++i) differing += b0[i] != b1[i];
  LT_CHECK(differing == 5);
}

LT_TEST(corrupt_blob_fails_cleanly) {
  auto blob = lt_files::read("cs30/calibration_0.bin");
  blob.resize(30);  // 截断
  LT_CHECK(!cs30::decode_calibration(blob.data(), blob.size()));
  const uint8_t junk[] = {0xff, 0xff, 0xff, 0xff};
  LT_CHECK(!cs30::decode_calibration(junk, sizeof(junk)));
  LT_CHECK(!cs30::decode_calibration(nullptr, 0));
}

LT_TEST_MAIN()
