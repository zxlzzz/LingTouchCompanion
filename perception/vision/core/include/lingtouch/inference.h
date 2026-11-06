// 推理后端与大模型接口（本次只定接口，不集成库）。
//
// - InferenceBackend：鸿蒙接 MindSpore Lite（系统内置，可用麒麟 NPU，有 C API），安卓接 ONNX Runtime。
// - LanguageModel：SpatialLM 的语言部分和 agent 共用，实现用 llama.cpp。
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "lingtouch/result.h"

namespace lingtouch {

enum class TensorType : uint8_t { kFloat32 = 1, kFloat16 = 2, kInt8 = 3, kInt32 = 4, kInt64 = 5 };

struct Tensor {
  std::string name;
  TensorType type = TensorType::kFloat32;
  std::vector<int64_t> shape;
  std::vector<uint8_t> data;  // 按 type 解释的原始字节
};

struct InferenceOptions {
  int threads = 0;          // 0 = 由后端决定
  bool prefer_npu = false;  // 鸿蒙上走 NNRt/NPU，安卓上走 NNAPI/QNN 等，由实现决定能否满足
};

class InferenceBackend {
 public:
  virtual ~InferenceBackend() = default;
  virtual std::string name() const = 0;  // 例如 "mindspore-lite"、"onnxruntime"
  virtual Status load(const std::string& model_path, const InferenceOptions& options) = 0;
  virtual Result<std::vector<Tensor>> run(const std::vector<Tensor>& inputs) = 0;
};

struct GenerationOptions {
  int max_tokens = 256;
  double temperature = 0.0;
  uint64_t seed = 0;
};

class LanguageModel {
 public:
  virtual ~LanguageModel() = default;
  virtual Status load(const std::string& model_path) = 0;
  // on_token 返回 false 时提前结束
  virtual Result<std::string> generate(const std::string& prompt, const GenerationOptions& options,
                                       const std::function<bool(const std::string&)>& on_token) = 0;
};

}  // namespace lingtouch
