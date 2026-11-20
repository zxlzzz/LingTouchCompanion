#include "lingtouch/types.h"

namespace lingtouch {

const char* grid_status_name(GridStatus s) {
  switch (s) {
    case GridStatus::kOk:
      return "ok";
    case GridStatus::kNoFrame:
      return "no_frame";
    case GridStatus::kNoCalibration:
      return "no_calibration";
    case GridStatus::kGroundFitFailed:
      return "ground_fit_failed";
  }
  return "unknown";
}

}  // namespace lingtouch
