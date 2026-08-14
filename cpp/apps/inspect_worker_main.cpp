#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/host/host_fingerprint.hpp"
#include "perceptshift/inference/session_factory.hpp"
#include "perceptshift/version.hpp"

#include <CLI/CLI.hpp>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>

int main(int argc, char** argv) {
  CLI::App app{"perceptshift-inspect-worker"};
  bool print_version = false;
  bool host_only = false;
  bool json_out = true;
  std::string model_path;
  app.add_flag("--version", print_version, "Print version");
  app.add_flag("--host", host_only, "Inspect host only");
  app.add_flag("--json", json_out, "Emit JSON (default)");
  app.add_option("--model", model_path, "ONNX model path");
  CLI11_PARSE(app, argc, argv);

  if (print_version) {
    std::cout << perceptshift::kVersionString << "\n";
    return 0;
  }

  nlohmann::json out;
  out["schema_version"] = "1.0";
  out["document_type"] = "perceptshift.inspect_report";
  out["product_version"] = perceptshift::kVersionString;
  out["host"] = nlohmann::json::parse(
      perceptshift::host::host_fingerprint_to_json(perceptshift::host::collect_host_fingerprint()));

  if (host_only || model_path.empty()) {
    out["model"] = nullptr;
    out["status"] = "ok";
    std::cout << out.dump(2) << "\n";
    return 0;
  }

#if !PERCEPTSHIFT_HAS_ONNXRUNTIME
  out["status"] = "error";
  out["error"] = {
      {"code", "MODEL_PROVIDER_UNAVAILABLE"},
      {"message", "ONNX Runtime not linked into this build"},
  };
  std::cerr << out.dump() << "\n";
  return 3;
#else
  perceptshift::inference::SessionCreateRequest req;
  req.model_path = model_path;
  req.security.allow_symlinks = false;
  req.security.require_owner_match = false;
  req.options.provider_order = {"CPUExecutionProvider"};
  auto session = perceptshift::inference::create_onnx_session(req);
  if (!session) {
    out["status"] = "error";
    out["error"] = {
        {"code", perceptshift::to_string(session.error().code)},
        {"message", session.error().message},
    };
    std::cerr << out.dump() << "\n";
    return 5;
  }
  const auto& meta = session.value()->metadata();
  nlohmann::json model;
  model["path"] = meta.model_path;
  model["sha256"] = meta.model_sha256;
  model["onnxruntime_version"] = meta.onnxruntime_version;
  model["available_providers"] = meta.available_providers;
  model["inputs"] = nlohmann::json::array();
  for (const auto& t : meta.inputs) {
    model["inputs"].push_back({
        {"name", t.name},
        {"element_type", perceptshift::inference::to_string(t.element_type)},
        {"shape", t.shape},
    });
  }
  model["outputs"] = nlohmann::json::array();
  for (const auto& t : meta.outputs) {
    model["outputs"].push_back({
        {"name", t.name},
        {"element_type", perceptshift::inference::to_string(t.element_type)},
        {"shape", t.shape},
    });
  }
  auto dig = perceptshift::crypto::sha256_file_hex(model_path);
  if (dig) {
    model["sha256"] = dig.value();
  }
  out["model"] = model;
  out["status"] = "ok";
  std::cout << out.dump(2) << "\n";
  return 0;
#endif
}
