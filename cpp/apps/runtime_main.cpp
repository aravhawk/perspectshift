#include "perceptshift/bundle/bundle_loader.hpp"
#include "perceptshift/host/host_fingerprint.hpp"
#include "perceptshift/runtime/runtime_engine.hpp"
#include "perceptshift/version.hpp"

#include <CLI/CLI.hpp>
#include <atomic>
#include <csignal>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>

namespace {
std::atomic<bool> g_stop{false};
void on_signal(int) {
  g_stop.store(true);
}
} // namespace

int main(int argc, char** argv) {
  CLI::App app{"perceptshift-runtime"};
  bool print_version = false;
  bool doctor = false;
  bool verify_bundle = false;
  bool json_out = false;
  std::string bundle_path;
  std::string policy_path;
  std::string verify_key;
  std::string signature_policy = "optional";
  std::string input_manifest;
  std::string results_jsonl = "results.jsonl";
  std::string telemetry_jsonl = "telemetry.jsonl";
  std::string input_mode;
  app.add_flag("--version", print_version, "Print version");
  app.add_flag("--doctor", doctor, "Inspect host fingerprint without model execution");
  app.add_flag("--verify-bundle", verify_bundle,
               "Verify bundle integrity/signatures without inference");
  app.add_flag("--json", json_out, "Emit JSON");
  app.add_option("--bundle", bundle_path, "Profile bundle path");
  app.add_option("--policy", policy_path, "Runtime policy JSON (enforced when provided)");
  app.add_option("--verify-key", verify_key, "Ed25519 public key (32 raw bytes or 64 hex chars)");
  app.add_option("--signature-policy", signature_policy, "disabled|optional|required");
  app.add_option("--input-manifest", input_manifest, "Finite offline stream manifest JSON");
  app.add_option("--results-jsonl", results_jsonl, "Results JSONL output path");
  app.add_option("--telemetry-jsonl", telemetry_jsonl, "Telemetry JSONL output path");
  app.add_option("--input", input_mode,
                 "Legacy smoke input mode (zeros|none); prefer --input-manifest");
  CLI11_PARSE(app, argc, argv);

  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);

  if (print_version) {
    std::cout << perceptshift::kProductName << " " << perceptshift::kVersionString << " ("
              << perceptshift::kGitCommit << ")\n";
    return 0;
  }
  if (doctor) {
    const auto fp = perceptshift::host::collect_host_fingerprint();
    std::cout << perceptshift::host::host_fingerprint_to_json(fp) << "\n";
    return 0;
  }
  if (bundle_path.empty()) {
    std::cerr << nlohmann::json({{"error",
                                  {{"code", "CONFIG_INVALID"},
                                   {"message", "requires --bundle (or use --doctor)"}}}})
              << "\n";
    return 2;
  }

  auto policy = perceptshift::bundle::parse_signature_policy(signature_policy);
  if (!policy) {
    std::cerr << nlohmann::json({{"error",
                                  {{"code", perceptshift::to_string(policy.error().code)},
                                   {"message", policy.error().message}}}})
              << "\n";
    return 2;
  }

  if (verify_bundle) {
    perceptshift::bundle::BundleLoadOptions opts;
    opts.signature_policy = policy.value();
    if (!verify_key.empty()) {
      auto key = perceptshift::bundle::load_ed25519_public_key(verify_key);
      if (!key) {
        std::cerr << nlohmann::json({{"error",
                                      {{"code", perceptshift::to_string(key.error().code)},
                                       {"message", key.error().message}}}})
                  << "\n";
        return 2;
      }
      opts.verify_public_key = std::move(key.value());
    } else if (opts.signature_policy == perceptshift::bundle::SignaturePolicy::Required) {
      std::cerr << nlohmann::json(
                       {{"error",
                         {{"code", "SIGNATURE_REQUIRED"},
                          {"message", "--verify-key required when signature-policy=required"}}}})
                << "\n";
      return 2;
    }
    auto report = perceptshift::bundle::verify_bundle_report(bundle_path, opts);
    if (!report) {
      std::cerr << nlohmann::json({{"error",
                                    {{"code", perceptshift::to_string(report.error().code)},
                                     {"message", report.error().message}}}})
                << "\n";
      return 4;
    }
    std::cout << report.value().dump(json_out ? 2 : -1) << "\n";
    return 0;
  }

#if !PERCEPTSHIFT_HAS_ONNXRUNTIME
  std::cerr << nlohmann::json({{"error",
                                {{"code", "MODEL_PROVIDER_UNAVAILABLE"},
                                 {"message", "ONNX Runtime not linked into this build"}}}})
            << "\n";
  return 3;
#else
  perceptshift::runtime::RuntimeEngineConfig cfg;
  cfg.bundle_path = bundle_path;
  if (!policy_path.empty()) {
    cfg.policy_path = policy_path;
  }
  cfg.signature_policy = policy.value();
  if (!verify_key.empty()) {
    cfg.verify_key_path = verify_key;
  }
  cfg.allow_zeros_smoke = (input_mode == "zeros" || input_mode.empty()) && input_manifest.empty();

  perceptshift::runtime::RuntimeEngine engine;
  auto configured = engine.configure(cfg);
  if (!configured) {
    std::cerr << nlohmann::json({{"error",
                                  {{"code", perceptshift::to_string(configured.error().code)},
                                   {"message", configured.error().message}}}})
              << "\n";
    return 6;
  }
  auto warmed = engine.load_and_warmup();
  if (!warmed) {
    std::cerr << nlohmann::json({{"error",
                                  {{"code", perceptshift::to_string(warmed.error().code)},
                                   {"message", warmed.error().message}}}})
              << "\n";
    return 7;
  }

  if (!input_manifest.empty()) {
    auto results = engine.execute_input_manifest(input_manifest);
    if (!results) {
      std::cerr << nlohmann::json({{"error",
                                    {{"code", perceptshift::to_string(results.error().code)},
                                     {"message", results.error().message}}}})
                << "\n";
      return 9;
    }
    std::ofstream results_out(results_jsonl);
    std::ofstream telemetry_out(telemetry_jsonl);
    for (const auto& fr : results.value()) {
      nlohmann::json row{
          {"sample_id", fr.sample_id},
          {"ok", fr.ok},
          {"active_profile_id", fr.active_profile_id},
          {"inference_ms", fr.inference_ms},
          {"total_ms", fr.total_ms},
          {"control_hold", fr.control_hold},
      };
      results_out << row.dump() << "\n";
      telemetry_out << fr.telemetry.dump() << "\n";
    }
    auto st = engine.status_json();
    st["mode"] = "finite-stream";
    st["results_jsonl"] = results_jsonl;
    st["telemetry_jsonl"] = telemetry_jsonl;
    std::cout << st.dump(json_out ? 2 : -1) << "\n";
    return g_stop.load() ? 130 : 0;
  }

  nlohmann::json report = engine.status_json();
  report["status"] = "ok";
  report["product_version"] = perceptshift::kVersionString;
  report["policy_loaded"] = !policy_path.empty();

  if (input_mode != "none") {
    perceptshift::runtime::FrameRequest req;
    req.sample_id = "smoke";
    req.sequence_id = 1;
    req.kind = perceptshift::runtime::FrameInputKind::ZerosSmoke;
    auto fr = engine.execute_frame(req);
    if (!fr) {
      std::cerr << nlohmann::json({{"error",
                                    {{"code", perceptshift::to_string(fr.error().code)},
                                     {"message", fr.error().message}}}})
                << "\n";
      return 9;
    }
    report["inference"] = {
        {"ok", fr.value().ok},
        {"inference_ms", fr.value().inference_ms},
        {"total_ms", fr.value().total_ms},
        {"control_hold", fr.value().control_hold},
        {"control_hold_reason", fr.value().control_hold_reason},
        {"health_state", perceptshift::runtime::to_string(fr.value().health_state)},
        {"active_profile_id", fr.value().active_profile_id},
        {"active_provider_summary", fr.value().active_provider_summary},
    };
    if (!fr.value().ok) {
      std::cerr << report.dump(2) << "\n";
      return 9;
    }
  }

  if (json_out) {
    std::cout << report.dump(2) << "\n";
  } else {
    std::cout << "runtime ok"
              << " control_hold=" << (engine.control_hold_active() ? "true" : "false")
              << " ready=" << (engine.ready() ? "true" : "false") << "\n";
  }
  return g_stop.load() ? 130 : 0;
#endif
}
