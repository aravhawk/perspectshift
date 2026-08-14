#include "perceptshift/adapters/adapter_factory.hpp"
#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/image/preprocess_config.hpp"
#include "perceptshift/inference/session_factory.hpp"
#include "perceptshift/runtime/profile_executor.hpp"
#include "perceptshift/util/steady_clock.hpp"
#include "perceptshift/version.hpp"

#include <CLI/CLI.hpp>
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <nlohmann/json.hpp>
#include <sys/resource.h>
#include <vector>

#if defined(__linux__)
#include <unistd.h>
#endif

namespace {

[[nodiscard]] double peak_rss_mb_self() {
#if defined(__linux__)
  std::ifstream status("/proc/self/status");
  std::string key;
  while (status >> key) {
    if (key == "VmHWM:") {
      long kb = 0;
      status >> kb;
      return static_cast<double>(kb) / 1024.0;
    }
    status.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
  }
#endif
  rusage usage{};
  if (getrusage(RUSAGE_SELF, &usage) != 0) {
    return -1.0;
  }
#if defined(__APPLE__)
  return static_cast<double>(usage.ru_maxrss) / (1024.0 * 1024.0);
#else
  return static_cast<double>(usage.ru_maxrss) / 1024.0;
#endif
}

} // namespace

namespace {

nlohmann::json load_json(const std::string& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("unable to open " + path);
  }
  nlohmann::json j;
  in >> j;
  return j;
}

std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("unable to open sample: " + path.string());
  }
  in.seekg(0, std::ios::end);
  const auto size = in.tellg();
  in.seekg(0, std::ios::beg);
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
  if (!bytes.empty()) {
    in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
  }
  return bytes;
}

int session_int(const nlohmann::json& session, const char* key, int fallback) {
  if (!session.contains(key) || session[key].is_null()) {
    return fallback;
  }
  if (session[key].is_number_integer()) {
    return session[key].get<int>();
  }
  return fallback;
}

struct DatasetSample {
  std::string sample_id;
  std::filesystem::path path;
  bool is_image{false};
  std::string pixel_format{"rgb8"};
  std::size_t width{0};
  std::size_t height{0};
  std::size_t stride_bytes{0};
};

std::filesystem::path resolve_sample_path(const std::filesystem::path& dataset_path,
                                          const std::string& rel) {
  if (rel.empty()) {
    return {};
  }
  std::filesystem::path p(rel);
  if (p.is_absolute()) {
    return p;
  }
  const auto cwd = std::filesystem::current_path();
  const auto from_cwd = cwd / p;
  if (std::filesystem::is_regular_file(from_cwd)) {
    return from_cwd;
  }
  const auto from_dataset_dir = dataset_path.parent_path() / p;
  if (std::filesystem::is_regular_file(from_dataset_dir)) {
    return from_dataset_dir;
  }
  const auto from_workspace = dataset_path.parent_path().parent_path() / p;
  if (std::filesystem::is_regular_file(from_workspace)) {
    return from_workspace;
  }
  return from_cwd;
}

DatasetSample sample_from_json(const nlohmann::json& s, int idx,
                               const std::filesystem::path& dataset_path,
                               const std::string& adapter_name) {
  DatasetSample ds;
  ds.sample_id = s.value("sample_id", "sample-" + std::to_string(idx));
  const std::string input_kind = s.value("input_kind", "");
  const bool has_image = s.contains("image_path") && s["image_path"].is_string();
  const bool has_tensor = s.contains("tensor_path") && s["tensor_path"].is_string();
  if (!has_image && !has_tensor) {
    throw std::runtime_error("sample " + ds.sample_id + " missing tensor_path/image_path");
  }
  ds.width = static_cast<std::size_t>(s.value("width", s.value("source_width", 0)));
  ds.height = static_cast<std::size_t>(s.value("height", s.value("source_height", 0)));
  ds.stride_bytes = static_cast<std::size_t>(s.value("stride_bytes", 0));
  ds.pixel_format = s.value("pixel_format", "rgb8");

  // Explicit input_kind wins. raw_image must not silently fall back to tensor_path.
  if (input_kind == "raw_image") {
    if (!has_image) {
      throw std::runtime_error("sample " + ds.sample_id +
                               " input_kind=raw_image requires image_path");
    }
    if (ds.width == 0 || ds.height == 0) {
      throw std::runtime_error("sample " + ds.sample_id +
                               " raw_image requires width/height (or source_width/source_height)");
    }
    ds.is_image = true;
    ds.path = resolve_sample_path(dataset_path, s["image_path"].get<std::string>());
    return ds;
  }
  if (input_kind == "raw_tensor") {
    if (!has_tensor) {
      throw std::runtime_error("sample " + ds.sample_id +
                               " input_kind=raw_tensor requires tensor_path");
    }
    ds.is_image = false;
    ds.path = resolve_sample_path(dataset_path, s["tensor_path"].get<std::string>());
    return ds;
  }

  const bool image_adapter =
      adapter_name == "image_classification" || adapter_name == "yolo_v8_detection";
  if (image_adapter && has_image && ds.width > 0 && ds.height > 0) {
    ds.is_image = true;
    ds.path = resolve_sample_path(dataset_path, s["image_path"].get<std::string>());
    return ds;
  }
  if (has_tensor) {
    ds.is_image = false;
    ds.path = resolve_sample_path(dataset_path, s["tensor_path"].get<std::string>());
    return ds;
  }
  ds.is_image = true;
  ds.path = resolve_sample_path(dataset_path, s["image_path"].get<std::string>());
  return ds;
}

std::vector<DatasetSample> load_dataset_stream(const std::filesystem::path& dataset_path,
                                               bool allow_synthetic_smoke,
                                               int* synthetic_count_out,
                                               const std::string& adapter_name) {
  *synthetic_count_out = 0;
  std::ifstream in(dataset_path);
  if (!in) {
    throw std::runtime_error("unable to open dataset: " + dataset_path.string());
  }

  nlohmann::json root;
  try {
    in >> root;
  } catch (const nlohmann::json::exception&) {
    in.clear();
    in.seekg(0);
    root = nullptr;
  }

  if (root.is_object()) {
    if (root.contains("synthetic_float_samples")) {
      if (!allow_synthetic_smoke) {
        throw std::runtime_error(
            "dataset contains synthetic_float_samples; pass --allow-synthetic-smoke for named "
            "smoke only (production path requires samples with tensor_path)");
      }
      *synthetic_count_out = root["synthetic_float_samples"].get<int>();
      return {};
    }
    std::vector<DatasetSample> samples;
    if (root.contains("samples") && root["samples"].is_array()) {
      int idx = 0;
      for (const auto& s : root["samples"]) {
        samples.push_back(sample_from_json(s, idx++, dataset_path, adapter_name));
      }
      return samples;
    }
  }

  in.clear();
  in.seekg(0);
  std::vector<DatasetSample> samples;
  std::string line;
  int idx = 0;
  while (std::getline(in, line)) {
    if (line.empty())
      continue;
    samples.push_back(sample_from_json(nlohmann::json::parse(line), idx++, dataset_path, adapter_name));
  }
  if (samples.empty()) {
    throw std::runtime_error(
        "dataset stream empty; expected {\"samples\":[...]} or JSONL with tensor_path entries");
  }
  return samples;
}

} // namespace

int main(int argc, char** argv) {
  CLI::App app{"perceptshift-bench-worker"};
  bool print_version = false;
  bool allow_synthetic_smoke = false;
  std::string candidate_path;
  std::string dataset_path;
  int warmup = 1;
  int measured = 1;
  app.add_flag("--version", print_version, "Print version");
  app.add_flag("--allow-synthetic-smoke", allow_synthetic_smoke,
               "Permit synthetic_float_samples zero-filled smoke (non-production)");
  app.add_option("--candidate", candidate_path, "Candidate manifest path")->required(false);
  app.add_option("--dataset", dataset_path, "Dataset stream/manifest path");
  app.add_option("--warmup", warmup, "Warmup iterations");
  app.add_option("--measured", measured, "Measured iterations (used only with synthetic smoke)");
  CLI11_PARSE(app, argc, argv);

  if (print_version) {
    std::cout << perceptshift::kVersionString << "\n";
    return 0;
  }
  if (candidate_path.empty()) {
    std::cerr << nlohmann::json({{"status", "error"},
                                 {"code", "CONFIG_INVALID"},
                                 {"message", "missing --candidate"}})
              << "\n";
    return 2;
  }

#if !PERCEPTSHIFT_HAS_ONNXRUNTIME
  std::cerr << nlohmann::json({{"status", "error"},
                               {"code", "MODEL_PROVIDER_UNAVAILABLE"},
                               {"message", "ONNX Runtime not linked into this build"}})
            << "\n";
  return 3;
#else
  try {
    const auto candidate = load_json(candidate_path);
    const std::string model_path =
        candidate.value("model_absolute_path", candidate.value("model_path", ""));
    if (model_path.empty()) {
      throw std::runtime_error("candidate missing model_absolute_path/model_path");
    }
    std::string expected_sha = candidate.value("model_sha256", "");

    perceptshift::inference::SessionCreateRequest req;
    req.model_path = model_path;
    if (!expected_sha.empty()) {
      req.expected_sha256 = expected_sha;
    }
    req.security.require_owner_match = false;
    req.security.allow_symlinks = false;
    if (candidate.contains("session")) {
      const auto& session = candidate["session"];
      if (session.contains("provider_order")) {
        req.options.provider_order = session["provider_order"].get<std::vector<std::string>>();
      }
      req.options.intra_op_threads = session_int(session, "intra_op_threads", 1);
      req.options.inter_op_threads = session_int(session, "inter_op_threads", 1);
      req.options.graph_optimization_level = session.value("graph_optimization_level", "all");
      req.options.allow_intra_op_spinning = session.value("allow_intra_op_spinning", false);
      req.options.xnnpack_intra_op_threads =
          std::max(1, session_int(session, "xnnpack_threads",
                                  session_int(session, "xnnpack_intra_op_threads", 1)));
    }

    auto session = perceptshift::inference::create_onnx_session(req);
    if (!session) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", perceptshift::to_string(session.error().code)},
                                   {"message", session.error().message}})
                << "\n";
      return 4;
    }
    auto warm = session.value()->warmup(std::max(0, warmup));
    if (!warm) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", "PROFILE_WARMUP_FAILED"},
                                   {"message", warm.error().message}})
                << "\n";
      return 5;
    }

    std::string adapter_name = "raw_tensor";
    nlohmann::json adapter_config = nlohmann::json::object();
    if (candidate.contains("adapter") && candidate["adapter"].is_object()) {
      adapter_name = candidate["adapter"].value("name", adapter_name);
      if (candidate["adapter"].contains("config")) {
        adapter_config = candidate["adapter"]["config"];
      }
    }
    auto adapter = perceptshift::adapters::create_adapter(adapter_name, adapter_config);
    if (!adapter) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", "CONFIG_INVALID"},
                                   {"message", adapter.error().message}})
                << "\n";
      return 2;
    }

    perceptshift::image::PreprocessConfig preprocess{};
    if (candidate.contains("preprocess") && candidate["preprocess"].is_object()) {
      auto cfg = perceptshift::image::preprocess_config_from_json(candidate["preprocess"]);
      if (!cfg) {
        // Transitional: if preprocess is incomplete, leave default for tensor-only paths.
        if (adapter_name != "raw_tensor") {
          std::cerr << nlohmann::json({{"status", "error"},
                                       {"code", "CONFIG_INVALID"},
                                       {"message", cfg.error().message}})
                    << "\n";
          return 2;
        }
      } else {
        preprocess = cfg.value();
      }
    }

    int synthetic_count = 0;
    std::vector<DatasetSample> dataset_samples;
    if (!dataset_path.empty()) {
      dataset_samples =
          load_dataset_stream(dataset_path, allow_synthetic_smoke, &synthetic_count, adapter_name);
    } else if (!allow_synthetic_smoke) {
      std::cerr << nlohmann::json(
                       {{"status", "error"},
                        {"code", "DATASET_INVALID"},
                        {"message",
                         "production bench-worker requires --dataset with tensor samples; "
                         "use --allow-synthetic-smoke only for named smoke"}})
                << "\n";
      return 2;
    } else {
      synthetic_count = std::max(1, measured);
    }

    const auto& meta = session.value()->metadata();
    nlohmann::json summary{
        {"status", "ok"},
        {"schema_version", "1.0"},
        {"document_type", "perceptshift.bench_worker_summary"},
        {"candidate_id", candidate.value("candidate_id", "")},
        {"model_path", model_path},
        {"model_sha256", meta.model_sha256},
        {"latency_definition", "profile_executor_complete"},
        {"provider_report",
         {
             {"requested_providers", session.value()->provider_report().requested_providers},
             {"registered_providers", session.value()->provider_report().registered_providers},
             {"warnings", session.value()->provider_report().warnings},
             {"xnnpack_node_fraction", nullptr},
             {"xnnpack_fraction_unavailable_reason",
              session.value()->provider_report().xnnpack_fraction_unavailable_reason},
             {"session_config",
              {
                  {"intra_op_threads", req.options.intra_op_threads},
                  {"inter_op_threads", req.options.inter_op_threads},
                  {"allow_intra_op_spinning", req.options.allow_intra_op_spinning},
                  {"graph_optimization_level", req.options.graph_optimization_level},
                  {"xnnpack_intra_op_threads", req.options.xnnpack_intra_op_threads},
                  {"provider_order", req.options.provider_order},
              }},
         }},
        {"samples", nlohmann::json::array()},
        {"detections", nlohmann::json::array()},
    };
    if (session.value()->provider_report().xnnpack_node_fraction.has_value()) {
      summary["provider_report"]["xnnpack_node_fraction"] =
          *session.value()->provider_report().xnnpack_node_fraction;
    }

    perceptshift::runtime::ProfileExecutor executor(session.value().get(), adapter.value().get(),
                                                    preprocess);

    const bool use_synthetic = synthetic_count > 0;
    const int iterations =
        use_synthetic ? std::max(1, synthetic_count) : static_cast<int>(dataset_samples.size());

    std::vector<double> executor_ms_values;
    executor_ms_values.reserve(static_cast<std::size_t>(iterations));
    for (int i = 0; i < iterations; ++i) {
      perceptshift::runtime::ProfileExecutorInput pin;
      pin.sequence_id = i;
      pin.allow_zeros_smoke = allow_synthetic_smoke;
      if (use_synthetic) {
        pin.kind = perceptshift::runtime::ProfileExecutorInput::Kind::ZerosSmoke;
        pin.sample_id = "synthetic-" + std::to_string(i);
      } else {
        const auto& ds = dataset_samples[static_cast<std::size_t>(i)];
        pin.sample_id = ds.sample_id;
        pin.payload = read_bytes(ds.path);
        if (ds.is_image) {
          pin.kind = perceptshift::runtime::ProfileExecutorInput::Kind::RawImageBytes;
          pin.pixel_format = ds.pixel_format;
          pin.width = ds.width;
          pin.height = ds.height;
          pin.stride_bytes = ds.stride_bytes;
          if (pin.width == 0 || pin.height == 0) {
            // Infer dimensions from payload for tightly packed rgb8 when metadata absent.
            if (pin.pixel_format == "rgb8" && (pin.payload.size() % 3) == 0) {
              // Require explicit dims for certification honesty.
              throw std::runtime_error("image sample " + ds.sample_id +
                                       " requires source_width/source_height");
            }
          }
        } else {
          pin.kind = perceptshift::runtime::ProfileExecutorInput::Kind::TensorBytes;
        }
      }

      auto result = executor.execute(pin);
      if (!result || !result.value().ok) {
        const auto& err = (!result) ? result.error() : result.value().error;
        std::cerr << nlohmann::json({{"status", "error"},
                                     {"code", "INFERENCE_FAILED"},
                                     {"message", err.message},
                                     {"sample_index", i}})
                  << "\n";
        return 6;
      }
      const auto& er = result.value();
      executor_ms_values.push_back(er.executor_ms);
      nlohmann::json sample{
          {"index", i},
          {"sample_id", pin.sample_id},
          {"preprocess_ms", er.preprocess_ms},
          {"inference_ms", er.inference_ms},
          {"postprocess_ms", er.postprocess_ms},
          {"executor_ms", er.executor_ms},
          {"preprocess_impl", er.preprocess_impl},
          {"ok", true},
          {"synthetic", use_synthetic},
          {"task", er.output.task},
      };
      // Emit production-equivalent normalized outputs for quality/certification.
      if (!er.output.classifications.empty()) {
        nlohmann::json classes = nlohmann::json::array();
        for (const auto& cls : er.output.classifications) {
          classes.push_back({{"class_id", cls.class_id}, {"score", cls.score}});
        }
        sample["classifications"] = classes;
        sample["top_class_id"] = er.output.classifications.front().class_id;
        sample["top_score"] = er.output.classifications.front().score;
      }
      if (!er.output.detections.empty()) {
        nlohmann::json dets = nlohmann::json::array();
        for (const auto& det : er.output.detections) {
          dets.push_back({
              {"class_id", det.class_id},
              {"confidence", det.score},
              {"bbox", {{"x", det.x}, {"y", det.y}, {"w", det.w}, {"h", det.h}}},
          });
        }
        sample["detections"] = dets;
        sample["source_width"] = er.transform.source_width;
        sample["source_height"] = er.transform.source_height;
      }
      if (!er.output.raw_values.empty()) {
        sample["raw_value_count"] = er.output.raw_values.size();
        const std::size_t preview = std::min<std::size_t>(er.output.raw_values.size(), 16);
        sample["raw_values_preview"] = nlohmann::json::array();
        for (std::size_t r = 0; r < preview; ++r) {
          sample["raw_values_preview"].push_back(er.output.raw_values[r]);
        }
      }
      if (er.output.confidence_signal >= 0.f) {
        sample["confidence_signal"] = er.output.confidence_signal;
      }
      summary["samples"].push_back(sample);
      if (er.output.task == "yolo_v8_detection") {
        for (const auto& det : er.output.detections) {
          summary["detections"].push_back({
              {"candidate_id", candidate.value("candidate_id", "")},
              {"sample_id", pin.sample_id},
              {"source_width", er.transform.source_width},
              {"source_height", er.transform.source_height},
              {"class_id", det.class_id},
              {"confidence", det.score},
              {"bbox", {{"x", det.x}, {"y", det.y}, {"w", det.w}, {"h", det.h}}},
              {"model_hash", meta.model_sha256},
          });
        }
      }
      std::cout << sample.dump() << "\n";
    }

    std::sort(executor_ms_values.begin(), executor_ms_values.end());
    auto pct = [&](double q) -> double {
      if (executor_ms_values.empty())
        return 0.0;
      const auto idx = static_cast<std::size_t>(
          std::clamp(q, 0.0, 1.0) * static_cast<double>(executor_ms_values.size() - 1));
      return executor_ms_values[idx];
    };
    double sum = 0.0;
    for (double v : executor_ms_values)
      sum += v;
    const double peak_rss = peak_rss_mb_self();
    summary["summary"] = {
        {"count", iterations},
        {"mean_executor_ms", sum / static_cast<double>(std::max(1, iterations))},
        {"p50_ms", pct(0.50)},
        {"p95_ms", pct(0.95)},
        {"p99_ms", pct(0.99)},
        {"latency_definition", "profile_executor_complete"},
        {"synthetic_smoke", use_synthetic},
    };
    if (peak_rss >= 0.0) {
      summary["peak_rss_mb"] = peak_rss;
#if defined(__linux__)
      summary["peak_rss_method"] = "proc_self_status_VmHWM";
#else
      summary["peak_rss_method"] = "getrusage_RUSAGE_SELF";
#endif
    } else {
      summary["peak_rss_mb"] = nullptr;
      summary["peak_rss_unavailable_reason"] = "unavailable.sensor";
    }
    std::cout << summary.dump() << "\n";
    return 0;
  } catch (const std::exception& ex) {
    std::cerr << nlohmann::json(
                     {{"status", "error"}, {"code", "CONFIG_INVALID"}, {"message", ex.what()}})
              << "\n";
    return 2;
  }
#endif
}
