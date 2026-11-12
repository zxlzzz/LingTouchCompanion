#pragma once

#include <memory>
#include <vector>
#include "lingtouch/perception/depth_geometry.h"

namespace lingtouch {

class DepthReview {
 public:
  explicit DepthReview(const Config& config);
  ~DepthReview();
  OccupancyGrid process(const DepthFrame& frame, const DepthCameraModel& camera,
                        const std::vector<std::vector<uint8_t>>& masks,
                        const std::vector<DepthFrame>* recent);

 private:
  struct State;
  std::unique_ptr<State> state_;
};

}  // namespace lingtouch
