#include "perceptshift/runtime/runtime_engine.hpp"

#include "perceptshift/adapters/adapter_factory.hpp"
#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/image/preprocess_config.hpp"
#include "perceptshift/inference/session_factory.hpp"
#include "perceptshift/runtime/policy_loader.hpp"
#include "perceptshift/runtime/profile_executor.hpp"
#include "perceptshift/util/file_security.hpp"
#include "perceptshift/util/steady_clock.hpp"
#include "perceptshift/version.hpp"

#include <algorithm>
#include <cstring>
#include <fstream>
#include <sstream>

namespace perceptshift::runtime {
namespace {

[[nodiscard]] Result<std::vector<std::uint8_t>> read_file_bytes(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return Error::make(ErrorCode::DatasetInvalid, "unable to open sample path: " + path.string());
  }
  in.seekg(0, std::ios::end);
  const auto size = in.tellg();
  if (size < 0) {
    return Error::make(ErrorCode::DatasetInvalid, "unable to size sample path: " + path.string());
  }
  in.seekg(0, std::ios::beg);
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
  if (!bytes.empty()) {
    in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (static_cast<std::size_t>(in.gcount()) != bytes.size()) {
      return Error::make(ErrorCode::DatasetInvalid, "short read for sample: " + path.string());
    }
  }
  return bytes;
}

[[nodiscard]] int session_int(const nlohmann::json& session, const char* key, int fallback) {
  if (!session.contains(key) || session[key].is_null()) {
    return fallback;
  }
  if (session[key].is_number_integer()) {
    return session[key].get<int>();
  }
  return fallback;
}

} // namespace

Result<void> RuntimeEngine::configure(const RuntimeEngineConfig& config) {
  configured_ = false;
  ready_ = false;
  bundle_.reset();
  registry_ = profiles::ProfileRegistry{};
  pool_.clear();
  controller_.reset();
  adapter_.reset();
  profile_docs_.clear();

  if (config.bundle_path.empty()) {
    return Error::make(ErrorCode::ConfigInvalid, "bundle_path is required");
  }
  config_ = config;

  bundle::BundleLoadOptions load_opts;
  load_opts.signature_policy = config.signature_policy;
  load_opts.strict_inventory = config.strict_inventory;
  load_opts.trusted_key_ids = config.trusted_key_ids;
  load_opts.security.allow_symlinks = config.allow_symlinks;
  load_opts.security.require_owner_match = false;
  if (config.verify_key_path.has_value()) {
    auto key = bundle::load_ed25519_public_key(*config.verify_key_path);
    if (!key) {
      return key.error();
    }
    load_opts.verify_public_key = std::move(key.value());
  } else if (config.signature_policy == bundle::SignaturePolicy::Required) {
    return Error::make(ErrorCode::SignatureRequired, "signature policy required needs --verify-key",
                       "Provide an Ed25519 public key path");
  }

  auto loaded = bundle::load_bundle(config.bundle_path, load_opts);
  if (!loaded) {
    return loaded.error();
  }
  bundle_ = std::move(loaded.value());

  policy_ = default_runtime_policy();
  if (!bundle_->runtime_policy_defaults.empty()) {
    policy_ = merge_runtime_policy(policy_, bundle_->runtime_policy_defaults);
  }
  if (config.policy_path.has_value()) {
    auto file_policy = load_runtime_policy_file(*config.policy_path);
    if (!file_policy) {
      return file_policy.error();
    }
    policy_ = file_policy.value();
  }
  if (!bundle_->quality_metric_name.empty()) {
    policy_.quality_metric_name = bundle_->quality_metric_name;
  }
  if (!bundle_->quality_direction.empty()) {
    policy_.quality_direction = bundle_->quality_direction;
  }

  std::string adapter_name = bundle_->adapter_name;
  nlohmann::json adapter_config = nlohmann::json::object();
  if (adapter_name.empty() && !bundle_->profile_documents.empty()) {
    const auto& first = bundle_->profile_documents.front();
    if (first.contains("adapter") && first["adapter"].is_object()) {
      adapter_name = first["adapter"].value("name", "raw_tensor");
      if (first["adapter"].contains("config") && first["adapter"]["config"].is_object()) {
        adapter_config = first["adapter"]["config"];
      }
    }
  }
  if (adapter_name.empty()) {
    adapter_name = "raw_tensor";
  }
  // Prefer schema-validated adapter config from the first certified profile when present.
  for (const auto& doc : bundle_->profile_documents) {
    if (doc.contains("adapter") && doc["adapter"].is_object()) {
      if (doc["adapter"].contains("config") && doc["adapter"]["config"].is_object()) {
        adapter_config = doc["adapter"]["config"];
      }
      if (adapter_name.empty()) {
        adapter_name = doc["adapter"].value("name", adapter_name);
      }
      break;
    }
  }
  auto adapter = adapters::create_adapter(adapter_name, adapter_config);
  if (!adapter) {
    return adapter.error();
  }
  adapter_ = std::move(adapter.value());

  for (std::size_t i = 0; i < bundle_->profiles.size(); ++i) {
    auto profile = bundle_->profiles[i];
    profile_docs_[profile.profile_id] = bundle_->profile_documents[i];
    if (profile.status != profiles::ProfileStatus::Certified) {
      continue;
    }
    if (!registry_.add(profile)) {
      return Error::make(ErrorCode::InternalInvariantFailed,
                         "failed to register profile " + profile.profile_id);
    }
  }
  if (registry_.size() == 0) {
    return Error::make(ErrorCode::NoEligibleProfile, "bundle has no certified profiles");
  }

  controller_ = std::make_unique<Controller>(policy_, &registry_);
  configured_ = true;
  return Result<void>::success();
}

Result<nlohmann::json> RuntimeEngine::verify_bundle_only() {
  if (!configured_ || !bundle_) {
    return Error::make(ErrorCode::ConfigInvalid, "engine is not configured");
  }
  nlohmann::json report{
      {"ok", true},
      {"document_type", "perceptshift.bundle_verify"},
      {"schema_version", "1.0"},
      {"bundle_id", bundle_->bundle_id},
      {"manifest_sha256", bundle_->manifest_sha256_hex},
      {"files_checked", bundle_->files.size()},
      {"certified_profiles", registry_.size()},
      {"signature",
       {
           {"present", bundle_->signature.present},
           {"verified", bundle_->signature.verified},
           {"algorithm", bundle_->signature.algorithm},
           {"key_id", bundle_->signature.key_id},
           {"policy", bundle::to_string(config_.signature_policy)},
       }},
      {"product_version", kVersionString},
  };
  return report;
}

Result<inference::SessionCreateRequest>
RuntimeEngine::session_request_for_profile(const profiles::Profile& profile,
                                           const nlohmann::json& profile_doc) const {
  inference::SessionCreateRequest req;
  req.model_path = bundle_->root / profile.model_relative_path;
  if (!profile.model_sha256.empty() &&
      profile.model_sha256.find_first_not_of('0') != std::string::npos) {
    req.expected_sha256 = profile.model_sha256;
  }
  req.security.require_owner_match = false;
  req.security.allow_symlinks = config_.allow_symlinks;
  req.security.allowed_roots = {bundle_->root};

  nlohmann::json session = nlohmann::json::object();
  if (profile_doc.contains("session") && profile_doc["session"].is_object()) {
    session = profile_doc["session"];
  }
  if (session.contains("provider_order") && session["provider_order"].is_array()) {
    req.options.provider_order = session["provider_order"].get<std::vector<std::string>>();
  }
  req.options.intra_op_threads = session_int(session, "intra_op_threads", 1);
  req.options.inter_op_threads = session_int(session, "inter_op_threads", 1);
  req.options.graph_optimization_level = session.value("graph_optimization_level", "all");
  req.options.allow_intra_op_spinning = session.value("allow_intra_op_spinning", false);
  // Map session.xnnpack_threads → xnnpack_intra_op_threads (coordinator contract).
  const int xnn_threads =
      session_int(session, "xnnpack_threads", session_int(session, "xnnpack_intra_op_threads", 1));
  req.options.xnnpack_intra_op_threads = std::max(1, xnn_threads);
  return req;
}

Result<void> RuntimeEngine::create_sessions() {
#if !PERCEPTSHIFT_HAS_ONNXRUNTIME
  return Error::make(ErrorCode::ModelProviderUnavailable,
                     "ONNX Runtime not linked into this build");
#else
  for (auto* profile : registry_.all()) {
    const auto& doc = profile_docs_.at(profile->profile_id);
    auto req = session_request_for_profile(*profile, doc);
    if (!req) {
      return req.error();
    }
    auto created = inference::create_onnx_session(req.value());
    if (!created) {
      return Error::make(created.error().code,
                         created.error().message + " (profile " + profile->profile_id + ")",
                         created.error().remediation);
    }
    auto warm = created.value()->warmup(std::max(0, config_.warmup_iterations));
    if (!warm) {
      return Error::make(ErrorCode::ProfileWarmupFailed, "warmup failed for profile " +
                                                             profile->profile_id + ": " +
                                                             warm.error().message);
    }
    auto inserted = pool_.insert(profile->profile_id, std::move(created.value()));
    if (!inserted) {
      return inserted.error();
    }
    controller_->mark_profile_warmed(profile->profile_id);
  }
  return Result<void>::success();
#endif
}

Result<void> RuntimeEngine::load_and_warmup() {
  if (!configured_) {
    return Error::make(ErrorCode::ConfigInvalid,
                       "configure() must be called before load_and_warmup");
  }
  ready_ = false;
  auto sessions = create_sessions();
  if (!sessions) {
    return sessions.error();
  }
  if (pool_.size() == 0) {
    return Error::make(ErrorCode::NoEligibleProfile, "no warmed sessions available");
  }
  const auto now = util::steady_now_ns();
  auto decision = controller_->evaluate_switch(now);
  if (!controller_->active_profile_id().has_value()) {
    return Error::make(
        ErrorCode::NoEligibleProfile, "controller selected no eligible profile after warmup",
        decision.evidence.empty() ? "Check deadline and offline envelopes" : decision.evidence);
  }
  ready_ = true;
  return Result<void>::success();
}

bool RuntimeEngine::control_hold_active() const {
  if (!controller_) {
    return true;
  }
  return controller_->health().control_hold_active();
}

nlohmann::json RuntimeEngine::status_json() const {
  nlohmann::json j{
      {"configured", configured_},
      {"ready", ready_},
      {"product_version", kVersionString},
      {"control_hold", control_hold_active()},
  };
  if (bundle_) {
    j["bundle_id"] = bundle_->bundle_id;
    j["loaded_profiles"] = pool_.size();
  }
  if (controller_) {
    j["health_state"] = to_string(controller_->health().state());
    j["control_hold_reason"] = controller_->health().control_hold_reason();
    if (controller_->active_profile_id()) {
      j["active_profile_id"] = *controller_->active_profile_id();
    }
  }
  return j;
}

Result<FrameResult> RuntimeEngine::run_active_inference(const FrameRequest& request) {
  FrameResult result;
  result.sequence_id = request.sequence_id;
  result.sample_id = request.sample_id;
  const auto t0 = util::steady_now_ns();

  if (!ready_ || !controller_) {
    result.error = Error::make(ErrorCode::ConfigInvalid, "runtime engine is not ready");
    result.health_state = HealthState::FailClosed;
    result.control_hold = true;
    result.control_hold_reason = "ENGINE_NOT_READY";
    return result;
  }

  const auto now =
      request.receive_steady_ns > 0 ? request.receive_steady_ns : util::steady_now_ns();
  auto switch_decision = controller_->evaluate_switch(now);
  result.last_switch_reason = switch_decision.reason;
  result.health_state = controller_->health().state();
  result.control_hold = controller_->health().control_hold_active();
  result.control_hold_reason = controller_->health().control_hold_reason();

  if (!controller_->active_profile_id().has_value() || result.control_hold) {
    result.ok = false;
    result.error =
        Error::make(ErrorCode::NoEligibleProfile,
                    result.control_hold_reason.empty()
                        ? "fail-closed: no eligible profile (control-hold request active)"
                        : result.control_hold_reason);
    result.telemetry = {
        {"control_hold", true},
        {"health_state", to_string(result.health_state)},
    };
    return result;
  }

  const std::string executed = *controller_->active_profile_id();
  // Capture provenance before execution; never overwrite after a post-frame switch.
  result.executed_profile_id = executed;
  result.active_profile_id = executed;
  result.next_active_profile_id = executed;
  auto sess = pool_.get(executed);
  if (!sess) {
    result.error = sess.error();
    return result;
  }

  const auto& doc = profile_docs_.at(executed);
  nlohmann::json preprocess_doc = nlohmann::json::object();
  if (doc.contains("preprocess") && doc["preprocess"].is_object()) {
    preprocess_doc = doc["preprocess"];
  }
  image::PreprocessConfig preprocess_cfg{};
  if (request.kind == FrameInputKind::RawImageBytes) {
    auto cfg = image::preprocess_config_from_json(preprocess_doc);
    if (!cfg) {
      result.error = cfg.error();
      return result;
    }
    preprocess_cfg = cfg.value();
  }

  ProfileExecutorInput pin;
  pin.sequence_id = request.sequence_id;
  pin.sample_id = request.sample_id;
  pin.trace_id = request.trace_id;
  pin.source_timestamp_ns = request.source_timestamp_ns;
  pin.receive_steady_ns = now;
  pin.allow_zeros_smoke = config_.allow_zeros_smoke;
  pin.payload = request.payload;
  pin.width = request.width;
  pin.height = request.height;
  pin.stride_bytes = request.stride_bytes;
  pin.pixel_format = request.pixel_format.empty() ? "rgb8" : request.pixel_format;
  if (request.kind == FrameInputKind::ZerosSmoke) {
    pin.kind = ProfileExecutorInput::Kind::ZerosSmoke;
  } else if (request.kind == FrameInputKind::TensorBytes) {
    pin.kind = ProfileExecutorInput::Kind::TensorBytes;
  } else if (request.kind == FrameInputKind::RawImageBytes) {
    pin.kind = ProfileExecutorInput::Kind::RawImageBytes;
  } else {
    result.error = Error::make(ErrorCode::InputUnsupported, "unsupported frame input kind");
    return result;
  }

  ProfileExecutor executor(sess.value(), adapter_.get(), preprocess_cfg);
  auto exec = executor.execute(pin);
  if (!exec) {
    result.error = exec.error();
    return result;
  }
  auto& er = exec.value();
  if (!er.ok) {
    FrameObservation obs;
    obs.now_steady_ns = util::steady_now_ns();
    obs.source_timestamp_ns = request.source_timestamp_ns;
    obs.inference_ok = false;
    obs.source_stale = request.source_stale;
    controller_->observe(obs);
    (void)controller_->evaluate_switch(obs.now_steady_ns);
    result.error = er.error;
    result.health_state = controller_->health().state();
    result.control_hold = controller_->health().control_hold_active();
    result.control_hold_reason = controller_->health().control_hold_reason();
    return result;
  }

  result.preprocess_ms = er.preprocess_ms;
  result.inference_ms = er.inference_ms;
  result.postprocess_ms = er.postprocess_ms;
  result.active_provider_summary = er.active_provider_summary;
  result.output = std::move(er.output);

  FrameObservation obs;
  obs.now_steady_ns = util::steady_now_ns();
  obs.source_timestamp_ns = request.source_timestamp_ns;
  obs.latency_ms = er.executor_ms;
  obs.inference_ok = true;
  obs.confidence_signal =
      request.confidence_hint >= 0.f ? request.confidence_hint : result.output.confidence_signal;
  obs.source_stale = request.source_stale;
  controller_->observe(obs);
  auto after = controller_->evaluate_switch(obs.now_steady_ns);
  result.last_switch_reason = after.reason;
  result.health_state = controller_->health().state();
  result.control_hold = controller_->health().control_hold_active();
  result.control_hold_reason = controller_->health().control_hold_reason();
  if (controller_->active_profile_id()) {
    result.next_active_profile_id = *controller_->active_profile_id();
  }
  // Keep active_profile_id as the profile that generated this frame.
  result.active_profile_id = result.executed_profile_id;

  const auto t1 = util::steady_now_ns();
  result.total_ms = static_cast<double>(t1 - t0) / 1.0e6;
  result.ok = !result.control_hold;
  result.telemetry = {
      {"executed_profile_id", result.executed_profile_id},
      {"next_active_profile_id", result.next_active_profile_id},
      {"active_profile_id", result.active_profile_id},
      {"preprocess_ms", result.preprocess_ms},
      {"inference_ms", result.inference_ms},
      {"postprocess_ms", result.postprocess_ms},
      {"executor_ms", er.executor_ms},
      {"latency_definition", "profile_executor_complete"},
      {"total_ms", result.total_ms},
      {"preprocess_impl", er.preprocess_impl},
      {"health_state", to_string(result.health_state)},
      {"control_hold", result.control_hold},
      {"active_provider_summary", result.active_provider_summary},
      {"tensor_contract", er.tensor_contract},
      {"policy_hash", controller_->policy_hash()},
  };
  if (result.control_hold) {
    result.error = Error::make(ErrorCode::NoEligibleProfile,
                               "fail-closed state active; control-hold request asserted");
  }
  return result;
}

Result<RuntimePolicy> RuntimeEngine::update_policy(const RuntimePolicy& next) {
  if (!controller_) {
    return Error::make(ErrorCode::ConfigInvalid, "controller not configured");
  }
  auto updated = controller_->update_policy(next);
  if (!updated) {
    return updated.error();
  }
  policy_ = updated.value();
  return policy_;
}

Result<FrameResult> RuntimeEngine::execute_frame(const FrameRequest& request) {
  auto result = run_active_inference(request);
  // run_active_inference returns FrameResult even on logical failure; propagate typed errors
  // only when the Result itself failed to construct (currently always ok wrapper).
  return result;
}

Result<std::vector<FrameResult>>
RuntimeEngine::execute_input_manifest(const std::filesystem::path& input_manifest_path) {
  if (!ready_) {
    return Error::make(ErrorCode::ConfigInvalid,
                       "engine must be load_and_warmup()'d before stream execution");
  }
  std::ifstream in(input_manifest_path);
  if (!in) {
    return Error::make(ErrorCode::DatasetInvalid,
                       "unable to open input manifest: " + input_manifest_path.string());
  }

  std::vector<nlohmann::json> samples;
  try {
    nlohmann::json root;
    in >> root;
    if (root.is_object() && root.contains("synthetic_float_samples")) {
      return Error::make(
          ErrorCode::DatasetInvalid,
          "synthetic_float_samples is not accepted on the production RuntimeEngine path",
          "Provide a dataset stream with samples[].tensor_path or samples[].image_path");
    }
    if (root.is_object() && root.contains("samples") && root["samples"].is_array()) {
      for (const auto& s : root["samples"]) {
        samples.push_back(s);
      }
    } else if (root.is_array()) {
      for (const auto& s : root) {
        samples.push_back(s);
      }
    } else {
      // JSONL: rewind and parse line by line.
      in.clear();
      in.seekg(0);
      std::string line;
      while (std::getline(in, line)) {
        if (line.empty())
          continue;
        samples.push_back(nlohmann::json::parse(line));
      }
    }
  } catch (const std::exception& ex) {
    return Error::make(ErrorCode::DatasetInvalid,
                       std::string("invalid input manifest: ") + ex.what());
  }

  if (samples.empty()) {
    return Error::make(ErrorCode::DatasetInvalid, "input manifest contains no samples");
  }

  const auto base_dir = input_manifest_path.parent_path();
  std::vector<FrameResult> results;
  results.reserve(samples.size());
  std::int64_t seq = 0;
  for (const auto& sample : samples) {
    if (!sample.is_object()) {
      return Error::make(ErrorCode::DatasetInvalid, "sample entry must be an object");
    }
    FrameRequest req;
    req.sequence_id = seq++;
    req.sample_id = sample.value("sample_id", "sample-" + std::to_string(req.sequence_id));
    req.receive_steady_ns = util::steady_now_ns();
    req.source_timestamp_ns = sample.value("source_timestamp_ns", req.receive_steady_ns);

    const std::string input_kind = sample.value("input_kind", "");
    const bool has_tensor = sample.contains("tensor_path") && sample["tensor_path"].is_string();
    const bool has_image = sample.contains("image_path") && sample["image_path"].is_string();

    auto resolve_path = [&](const std::string& rel_or_abs) -> std::filesystem::path {
      return (!rel_or_abs.empty() && rel_or_abs.front() == '/')
                 ? std::filesystem::path(rel_or_abs)
                 : (base_dir / rel_or_abs);
    };

    if (input_kind == "raw_image" ||
        (input_kind.empty() && has_image && !has_tensor) ||
        (input_kind.empty() && has_image && sample.value("prefer_image", false))) {
      if (!has_image) {
        return Error::make(ErrorCode::DatasetInvalid,
                           "sample " + req.sample_id + " input_kind=raw_image requires image_path");
      }
      // Never silently bypass preprocessing through tensor_path when raw_image is intended.
      auto bytes = read_file_bytes(resolve_path(sample["image_path"].get<std::string>()));
      if (!bytes) {
        return bytes.error();
      }
      req.kind = FrameInputKind::RawImageBytes;
      req.payload = std::move(bytes.value());
      req.width = sample.value("width", sample.value("source_width", static_cast<std::size_t>(0)));
      req.height = sample.value("height", sample.value("source_height", static_cast<std::size_t>(0)));
      req.stride_bytes = sample.value("stride_bytes", static_cast<std::size_t>(0));
      req.pixel_format = sample.value("pixel_format", "rgb8");
      if (req.width == 0 || req.height == 0) {
        return Error::make(ErrorCode::DatasetInvalid,
                           "sample " + req.sample_id +
                               " raw_image requires width/height or source_width/source_height");
      }
    } else if (input_kind == "raw_tensor" || (input_kind.empty() && has_tensor)) {
      if (!has_tensor) {
        return Error::make(ErrorCode::DatasetInvalid,
                           "sample " + req.sample_id +
                               " input_kind=raw_tensor requires tensor_path");
      }
      auto bytes = read_file_bytes(resolve_path(sample["tensor_path"].get<std::string>()));
      if (!bytes) {
        return bytes.error();
      }
      req.kind = FrameInputKind::TensorBytes;
      req.payload = std::move(bytes.value());
    } else if (sample.value("zeros_smoke", false) == true || input_kind == "zeros_smoke") {
      req.kind = FrameInputKind::ZerosSmoke;
    } else if (has_image) {
      // Ambiguous legacy: both tensor and image without input_kind — refuse silent tensor bypass
      // when an image adapter path is plausible.
      if (has_tensor) {
        return Error::make(
            ErrorCode::DatasetInvalid,
            "sample " + req.sample_id +
                " has both tensor_path and image_path; set input_kind to raw_tensor or raw_image");
      }
      auto bytes = read_file_bytes(resolve_path(sample["image_path"].get<std::string>()));
      if (!bytes) {
        return bytes.error();
      }
      req.kind = FrameInputKind::RawImageBytes;
      req.payload = std::move(bytes.value());
      req.width = sample.value("width", sample.value("source_width", static_cast<std::size_t>(0)));
      req.height = sample.value("height", sample.value("source_height", static_cast<std::size_t>(0)));
      req.stride_bytes = sample.value("stride_bytes", static_cast<std::size_t>(0));
      req.pixel_format = sample.value("pixel_format", "rgb8");
    } else {
      return Error::make(ErrorCode::DatasetInvalid,
                         "sample " + req.sample_id +
                             " requires input_kind raw_tensor/raw_image/zeros_smoke "
                             "(or tensor_path/image_path)");
    }

    auto frame = execute_frame(req);
    if (!frame) {
      return frame.error();
    }
    results.push_back(std::move(frame.value()));
  }
  return results;
}

} // namespace perceptshift::runtime
