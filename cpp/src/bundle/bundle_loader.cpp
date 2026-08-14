#include "perceptshift/bundle/bundle_loader.hpp"

#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/crypto/signature.hpp"
#include "perceptshift/util/file_security.hpp"
#include "perceptshift/version.hpp"

#include <algorithm>
#include <array>
#include <fstream>
#include <set>
#include <sstream>
#include <unordered_set>

namespace perceptshift::bundle {
namespace {

constexpr const char* kSupportedSchemaVersion = "1.0";
constexpr const char* kDocumentType = "perceptshift.profile_bundle";
constexpr const char* kSignatureAlgorithm = "ed25519";
constexpr const char* kPayloadSchemaVersion = "1.0";

[[nodiscard]] bool is_meta_relative_path(const std::string& rel) {
  return rel == "manifest.json" || rel == "manifest.sha256" || rel == "manifest.sig" ||
         rel == "manifest.sig.bin";
}

[[nodiscard]] Result<std::string> normalize_relative_path(const std::string& raw) {
  if (raw.empty()) {
    return Error::make(ErrorCode::PathUnsafe, "inventory path is empty");
  }
  if (raw.front() == '/' || (raw.size() >= 2 && raw[1] == ':')) {
    return Error::make(ErrorCode::PathUnsafe, "absolute inventory paths are rejected: " + raw,
                       "Use relative paths under the bundle root");
  }
  std::filesystem::path p(raw);
  if (p.is_absolute()) {
    return Error::make(ErrorCode::PathUnsafe, "absolute inventory paths are rejected: " + raw);
  }
  std::string normalized = p.lexically_normal().generic_string();
  if (normalized.empty() || normalized == "." || normalized == "/") {
    return Error::make(ErrorCode::PathUnsafe, "invalid inventory path: " + raw);
  }
  if (normalized.rfind("..", 0) == 0 || normalized.find("/../") != std::string::npos ||
      normalized.find("../") != std::string::npos || normalized.find("/..") != std::string::npos) {
    return Error::make(ErrorCode::PathUnsafe, "path traversal rejected: " + raw,
                       "Inventory paths must stay within the bundle root");
  }
  while (!normalized.empty() && normalized.front() == '/') {
    normalized.erase(normalized.begin());
  }
  return normalized;
}

[[nodiscard]] int hex_nibble(char c) {
  if (c >= '0' && c <= '9')
    return c - '0';
  if (c >= 'a' && c <= 'f')
    return c - 'a' + 10;
  if (c >= 'A' && c <= 'F')
    return c - 'A' + 10;
  return -1;
}

[[nodiscard]] Result<std::vector<std::uint8_t>> decode_hex_bytes(std::string_view hex,
                                                                 std::size_t expected_len) {
  if (hex.size() != expected_len * 2) {
    return Error::make(ErrorCode::SignatureInvalid, "hex payload length mismatch (expected " +
                                                        std::to_string(expected_len * 2) +
                                                        " chars)");
  }
  std::vector<std::uint8_t> out(expected_len);
  for (std::size_t i = 0; i < expected_len; ++i) {
    const int hi = hex_nibble(hex[i * 2]);
    const int lo = hex_nibble(hex[i * 2 + 1]);
    if (hi < 0 || lo < 0) {
      return Error::make(ErrorCode::SignatureInvalid, "invalid hex character in signature payload");
    }
    out[i] = static_cast<std::uint8_t>((hi << 4) | lo);
  }
  return out;
}

[[nodiscard]] Result<std::vector<std::uint8_t>> decode_base64(std::string_view encoded) {
  static constexpr unsigned char kDec[256] = {
      255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255,
      255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255,
      255, 255, 255, 255, 255, 62,  255, 255, 255, 63,  52,  53,  54,  55,  56,  57,  58,  59,  60,
      61,  255, 255, 255, 254, 255, 255, 255, 0,   1,   2,   3,   4,   5,   6,   7,   8,   9,   10,
      11,  12,  13,  14,  15,  16,  17,  18,  19,  20,  21,  22,  23,  24,  25,  255, 255, 255, 255,
      255, 255, 26,  27,  28,  29,  30,  31,  32,  33,  34,  35,  36,  37,  38,  39,  40,  41,  42,
      43,  44,  45,  46,  47,  48,  49,  50,  51,  255, 255, 255, 255, 255};
  std::vector<std::uint8_t> out;
  out.reserve(encoded.size() * 3 / 4);
  unsigned int buffer = 0;
  int bits = 0;
  for (unsigned char c : encoded) {
    if (c == '\n' || c == '\r' || c == ' ' || c == '\t') {
      continue;
    }
    const unsigned char v = kDec[c];
    if (v == 255) {
      return Error::make(ErrorCode::SignatureInvalid, "invalid base64 character in signature");
    }
    if (v == 254) { // '='
      break;
    }
    buffer = (buffer << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out.push_back(static_cast<std::uint8_t>((buffer >> bits) & 0xFF));
    }
  }
  return out;
}

[[nodiscard]] Result<nlohmann::json> read_json_file(const std::filesystem::path& path) {
  std::ifstream in(path);
  if (!in) {
    return Error::make(ErrorCode::ConfigInvalid, "unable to open " + path.filename().string());
  }
  try {
    nlohmann::json j;
    in >> j;
    return j;
  } catch (const std::exception& ex) {
    return Error::make(ErrorCode::ConfigInvalid, std::string("malformed JSON: ") + ex.what());
  }
}

[[nodiscard]] Result<std::vector<std::uint8_t>> read_bytes(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return Error::make(ErrorCode::PathUnsafe, "unable to read " + path.string());
  }
  in.seekg(0, std::ios::end);
  const auto size = in.tellg();
  if (size < 0) {
    return Error::make(ErrorCode::PathUnsafe, "unable to size " + path.string());
  }
  in.seekg(0, std::ios::beg);
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
  if (!bytes.empty()) {
    in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (static_cast<std::size_t>(in.gcount()) != bytes.size()) {
      return Error::make(ErrorCode::FileIntegrityFailed, "short read: " + path.string());
    }
  }
  return bytes;
}

[[nodiscard]] profiles::ProfileStatus parse_status(const std::string& status) {
  if (status == "certified")
    return profiles::ProfileStatus::Certified;
  if (status == "rejected")
    return profiles::ProfileStatus::Rejected;
  return profiles::ProfileStatus::Draft;
}

[[nodiscard]] profiles::Profile profile_from_json(const nlohmann::json& doc) {
  profiles::Profile p;
  p.profile_id = doc.value("profile_id", "");
  p.label = doc.value("label", p.profile_id);
  p.model_sha256 = doc.value("model_sha256", "");
  p.model_relative_path = doc.value("model_relative_path", "");
  p.status = parse_status(doc.value("status", "draft"));
  if (doc.contains("certified_quality") && doc["certified_quality"].is_number()) {
    p.certified_quality = doc["certified_quality"].get<double>();
  }
  if (doc.contains("certified_p99_ms") && doc["certified_p99_ms"].is_number()) {
    p.certified_p99_ms = doc["certified_p99_ms"].get<double>();
    p.offline_envelope_ms = p.certified_p99_ms;
  }
  if (doc.contains("latency_summary") && doc["latency_summary"].is_object()) {
    const auto& lat = doc["latency_summary"];
    if (lat.contains("p99_ms") && lat["p99_ms"].is_number()) {
      p.certified_p99_ms = lat["p99_ms"].get<double>();
      p.offline_envelope_ms = p.certified_p99_ms;
    }
    if (lat.contains("offline_envelope_ms") && lat["offline_envelope_ms"].is_number()) {
      p.offline_envelope_ms = lat["offline_envelope_ms"].get<double>();
    }
  }
  if (doc.contains("utility")) {
    if (doc["utility"].is_number()) {
      p.utility = doc["utility"].get<double>();
    } else if (doc["utility"].is_object() && doc["utility"].contains("score") &&
               doc["utility"]["score"].is_number()) {
      p.utility = doc["utility"]["score"].get<double>();
    }
  }
  if (doc.contains("peak_rss_summary") && doc["peak_rss_summary"].is_object() &&
      doc["peak_rss_summary"].contains("bytes") && doc["peak_rss_summary"]["bytes"].is_number()) {
    p.peak_rss_bytes = doc["peak_rss_summary"]["bytes"].get<std::int64_t>();
  }
  if (doc.contains("expected_cpu_features") && doc["expected_cpu_features"].is_array()) {
    p.required_cpu_features = doc["expected_cpu_features"].get<std::vector<std::string>>();
  }
  return p;
}

[[nodiscard]] int compare_semver(const std::string& a, const std::string& b) {
  auto parse = [](const std::string& s) {
    int major = 0;
    int minor = 0;
    int patch = 0;
    char dot = 0;
    std::istringstream iss(s);
    iss >> major >> dot >> minor >> dot >> patch;
    return std::array<int, 3>{major, minor, patch};
  };
  const auto av = parse(a);
  const auto bv = parse(b);
  if (av < bv)
    return -1;
  if (av > bv)
    return 1;
  return 0;
}

[[nodiscard]] Result<void> verify_signature(const std::filesystem::path& root,
                                            const BundleLoadOptions& options, SignatureInfo* info) {
  const auto sig_path = root / "manifest.sig";
  const bool present = std::filesystem::is_regular_file(sig_path);
  info->present = present;

  if (options.signature_policy == SignaturePolicy::Disabled) {
    return Result<void>::success();
  }
  if (!present) {
    if (options.signature_policy == SignaturePolicy::Required) {
      return Error::make(
          ErrorCode::SignatureRequired, "manifest.sig is required by signature policy",
          "Sign the bundle with Ed25519 or set signature policy to optional/disabled");
    }
    return Result<void>::success();
  }
  if (options.verify_public_key.empty()) {
    return Error::make(ErrorCode::SignatureRequired,
                       "signature present but --verify-key / public key was not provided",
                       "Pass a 32-byte Ed25519 public key (raw or 64-char hex)");
  }

  auto meta = read_json_file(sig_path);
  if (!meta) {
    return meta.error();
  }
  const auto& j = meta.value();
  info->algorithm = j.value("algorithm", "");
  info->key_id = j.value("key_id", "");
  info->payload_schema_version = j.value("payload_schema_version", "");
  info->encoding = j.value("encoding", "hex");

  if (info->algorithm != kSignatureAlgorithm) {
    return Error::make(ErrorCode::SignatureInvalid,
                       "unsupported signature algorithm: " + info->algorithm,
                       "Expected algorithm \"ed25519\"");
  }
  if (info->payload_schema_version != kPayloadSchemaVersion &&
      info->payload_schema_version != "1") {
    return Error::make(ErrorCode::SchemaUnsupported,
                       "unsupported signature payload_schema_version: " +
                           info->payload_schema_version);
  }
  if (!options.trusted_key_ids.empty()) {
    if (info->key_id.empty() ||
        std::find(options.trusted_key_ids.begin(), options.trusted_key_ids.end(), info->key_id) ==
            options.trusted_key_ids.end()) {
      return Error::make(ErrorCode::SignatureInvalid,
                         "signing key_id is not trusted: " + info->key_id,
                         "Use a key_id listed in the trusted verify-key set");
    }
  }

  std::vector<std::uint8_t> signature;
  if (info->encoding == "hex") {
    const std::string sig_hex = j.value("signature", "");
    auto decoded = decode_hex_bytes(sig_hex, 64);
    if (!decoded) {
      return decoded.error();
    }
    signature = std::move(decoded.value());
  } else if (info->encoding == "raw") {
    if (j.contains("signature") && j["signature"].is_string() &&
        !j["signature"].get<std::string>().empty()) {
      auto decoded = decode_base64(j["signature"].get<std::string>());
      if (!decoded) {
        return decoded.error();
      }
      signature = std::move(decoded.value());
    } else {
      const auto raw_path = root / "manifest.sig.bin";
      auto bytes = read_bytes(raw_path);
      if (!bytes) {
        return Error::make(ErrorCode::SignatureInvalid,
                           "encoding=raw requires signature base64 or manifest.sig.bin");
      }
      signature = std::move(bytes.value());
    }
    if (signature.size() != 64) {
      return Error::make(ErrorCode::SignatureInvalid, "Ed25519 signature must be 64 bytes");
    }
  } else {
    return Error::make(ErrorCode::SignatureInvalid,
                       "unsupported signature encoding: " + info->encoding,
                       "Use encoding hex or raw");
  }

  auto payload = read_bytes(root / "manifest.sha256");
  if (!payload) {
    return payload.error();
  }
  auto verified = crypto::ed25519_verify(options.verify_public_key, payload.value().data(),
                                         payload.value().size(), signature);
  if (!verified) {
    return verified.error();
  }
  info->verified = true;
  return Result<void>::success();
}

[[nodiscard]] Result<void> collect_strict_extras(const std::filesystem::path& root,
                                                 const std::set<std::string>& declared) {
  std::error_code ec;
  const auto options = std::filesystem::directory_options::skip_permission_denied;
  for (std::filesystem::recursive_directory_iterator it(root, options, ec), end; it != end;
       it.increment(ec)) {
    if (ec) {
      return Error::make(ErrorCode::PathUnsafe, "unable to walk bundle: " + ec.message());
    }
    if (it->is_symlink(ec)) {
      // Do not descend through symlinked directories; reject undeclared symlink files.
      if (it->is_directory(ec)) {
        it.disable_recursion_pending();
      }
    }
    if (!it->is_regular_file(ec) && !(it->is_symlink(ec) && !it->is_directory(ec))) {
      continue;
    }
    auto within = util::ensure_within_root(root, it->path());
    if (!within) {
      return Error::make(ErrorCode::PathUnsafe,
                         "bundle walk encountered path outside root: " + it->path().string());
    }
    const auto rel = std::filesystem::relative(it->path(), root, ec).generic_string();
    if (ec) {
      return Error::make(ErrorCode::PathUnsafe, "unable to relativize " + it->path().string());
    }
    if (is_meta_relative_path(rel)) {
      continue;
    }
    if (declared.count(rel) == 0) {
      return Error::make(ErrorCode::FileIntegrityFailed,
                         "undeclared file in strict inventory mode: " + rel,
                         "Add the file to the bundle inventory or remove it");
    }
  }
  return Result<void>::success();
}

} // namespace

Result<SignaturePolicy> parse_signature_policy(std::string_view text) {
  if (text == "disabled")
    return SignaturePolicy::Disabled;
  if (text == "optional")
    return SignaturePolicy::Optional;
  if (text == "required")
    return SignaturePolicy::Required;
  return Error::make(ErrorCode::ConfigInvalid, "invalid signature policy: " + std::string(text),
                     "Use disabled, optional, or required");
}

Result<std::vector<std::uint8_t>> load_ed25519_public_key(const std::filesystem::path& path) {
  auto bytes = read_bytes(path);
  if (!bytes) {
    return bytes.error();
  }
  auto& raw = bytes.value();
  if (raw.size() == 32) {
    return raw;
  }
  // Trim whitespace/newlines then interpret as hex.
  std::string text(raw.begin(), raw.end());
  while (!text.empty() && (text.back() == '\n' || text.back() == '\r' || text.back() == ' ' ||
                           text.back() == '\t')) {
    text.pop_back();
  }
  if (!text.empty() && text.front() == ' ') {
    // fall through
  }
  // Strip all whitespace for hex form.
  std::string hex;
  hex.reserve(text.size());
  for (char c : text) {
    if (c == ' ' || c == '\n' || c == '\r' || c == '\t')
      continue;
    hex.push_back(c);
  }
  if (hex.size() == 64) {
    return decode_hex_bytes(hex, 32);
  }
  return Error::make(ErrorCode::ConfigInvalid,
                     "Ed25519 public key must be 32 raw bytes or 64 hex characters",
                     "Write the verify key as raw binary or lowercase/uppercase hex");
}

Result<LoadedBundle> load_bundle(const std::filesystem::path& bundle_root,
                                 const BundleLoadOptions& options) {
  std::error_code ec;
  if (!std::filesystem::is_directory(bundle_root, ec)) {
    return Error::make(ErrorCode::ConfigInvalid, "bundle root is not a directory");
  }

  BundleLoadOptions opts = options;
  opts.security.allowed_roots = {bundle_root};
  opts.security.allow_symlinks = options.security.allow_symlinks;
  opts.security.require_owner_match = options.security.require_owner_match;

  const auto manifest_path = bundle_root / "manifest.json";
  const auto digest_path = bundle_root / "manifest.sha256";
  if (!std::filesystem::is_regular_file(manifest_path, ec)) {
    return Error::make(ErrorCode::ConfigInvalid, "manifest.json missing");
  }
  if (!std::filesystem::is_regular_file(digest_path, ec)) {
    return Error::make(ErrorCode::FileIntegrityFailed, "manifest.sha256 missing");
  }

  // Reject symlink escape on meta files when symlinks disallowed; always contain after resolve.
  for (const auto& meta : {manifest_path, digest_path}) {
    auto contained = util::ensure_within_root(bundle_root, meta);
    if (!contained) {
      return contained.error();
    }
    if (!opts.security.allow_symlinks && std::filesystem::is_symlink(meta, ec)) {
      return Error::make(ErrorCode::PathUnsafe,
                         "symlinked meta file rejected: " + meta.filename().string());
    }
  }

  auto manifest = read_json_file(manifest_path);
  if (!manifest) {
    return manifest.error();
  }
  const auto& m = manifest.value();
  if (!m.is_object()) {
    return Error::make(ErrorCode::ConfigInvalid, "manifest.json must be an object");
  }
  if (m.value("schema_version", "") != kSupportedSchemaVersion) {
    return Error::make(ErrorCode::SchemaUnsupported,
                       "unsupported schema_version: " + m.value("schema_version", std::string{}),
                       "Use schema_version \"1.0\"");
  }
  if (m.value("document_type", "") != kDocumentType) {
    return Error::make(ErrorCode::SchemaUnsupported,
                       "unsupported document_type: " + m.value("document_type", std::string{}));
  }

  const std::string min_runtime = m.value("minimum_compatible_runtime_version", "0.0.0");
  if (compare_semver(kVersionString, min_runtime) < 0) {
    return Error::make(ErrorCode::ProfileIncompatible,
                       "runtime version " + std::string(kVersionString) +
                           " is below minimum_compatible_runtime_version " + min_runtime);
  }

  auto actual = crypto::sha256_file_hex(manifest_path);
  if (!actual) {
    return actual.error();
  }
  auto digest_bytes = read_bytes(digest_path);
  if (!digest_bytes) {
    return digest_bytes.error();
  }
  std::string expected(digest_bytes.value().begin(), digest_bytes.value().end());
  while (!expected.empty() &&
         (expected.back() == '\n' || expected.back() == '\r' || expected.back() == ' ')) {
    expected.pop_back();
  }
  // Accept "hex" or "hex  filename" forms.
  {
    const auto sp = expected.find_first_of(" \t");
    if (sp != std::string::npos) {
      expected = expected.substr(0, sp);
    }
  }
  if (expected.size() != 64) {
    return Error::make(ErrorCode::FileIntegrityFailed, "malformed manifest.sha256 digest");
  }
  for (char c : expected) {
    if (hex_nibble(c) < 0) {
      return Error::make(ErrorCode::FileIntegrityFailed, "malformed manifest.sha256 digest");
    }
  }
  if (expected != actual.value()) {
    return Error::make(ErrorCode::FileIntegrityFailed,
                       "manifest.sha256 does not match manifest.json",
                       "Regenerate the bundle or restore an untampered manifest");
  }

  LoadedBundle loaded;
  loaded.root = std::filesystem::weakly_canonical(bundle_root, ec);
  if (ec) {
    loaded.root = bundle_root;
  }
  loaded.manifest = m;
  loaded.manifest_sha256_hex = actual.value();
  loaded.bundle_id = m.value("bundle_id", "");
  if (m.contains("adapter") && m["adapter"].is_object()) {
    loaded.adapter_name = m["adapter"].value("name", "");
  }
  loaded.quality_metric_name = m.value("quality_metric_name", "");
  loaded.quality_direction = m.value("quality_direction", "higher_is_better");
  if (m.contains("runtime_policy_defaults") && m["runtime_policy_defaults"].is_object()) {
    loaded.runtime_policy_defaults = m["runtime_policy_defaults"];
  }

  if (!m.contains("profiles") || !m["profiles"].is_array() || m["profiles"].empty()) {
    return Error::make(ErrorCode::NoEligibleProfile, "bundle contains no profiles");
  }
  if (!m.contains("files") || !m["files"].is_array()) {
    return Error::make(ErrorCode::ConfigInvalid, "bundle manifest missing files inventory");
  }

  std::unordered_set<std::string> profile_ids;
  for (const auto& profile_doc : m["profiles"]) {
    if (!profile_doc.is_object()) {
      return Error::make(ErrorCode::ConfigInvalid, "profile entry must be an object");
    }
    auto profile = profile_from_json(profile_doc);
    if (profile.profile_id.empty()) {
      return Error::make(ErrorCode::ConfigInvalid, "profile_id is required");
    }
    if (!profile_ids.insert(profile.profile_id).second) {
      return Error::make(ErrorCode::ConfigInvalid, "duplicate profile_id: " + profile.profile_id);
    }
    if (profile.model_relative_path.empty()) {
      return Error::make(ErrorCode::ConfigInvalid,
                         "model_relative_path required for profile " + profile.profile_id);
    }
    auto model_rel = normalize_relative_path(profile.model_relative_path);
    if (!model_rel) {
      return model_rel.error();
    }
    profile.model_relative_path = model_rel.value();
    loaded.profiles.push_back(profile);
    loaded.profile_documents.push_back(profile_doc);
  }

  std::set<std::string> declared;
  std::unordered_set<std::string> seen_paths;
  for (const auto& entry : m["files"]) {
    if (!entry.is_object()) {
      return Error::make(ErrorCode::ConfigInvalid, "inventory entry must be an object");
    }
    const std::string raw_path = entry.value("path", entry.value("relative_path", ""));
    const std::string sha = entry.value("sha256", "");
    auto rel = normalize_relative_path(raw_path);
    if (!rel) {
      return rel.error();
    }
    if (!seen_paths.insert(rel.value()).second) {
      return Error::make(ErrorCode::ConfigInvalid, "duplicate inventory path: " + rel.value());
    }
    if (sha.size() != 64) {
      return Error::make(ErrorCode::FileIntegrityFailed,
                         "malformed inventory digest for " + rel.value());
    }
    for (char c : sha) {
      if (hex_nibble(c) < 0) {
        return Error::make(ErrorCode::FileIntegrityFailed,
                           "malformed inventory digest for " + rel.value());
      }
    }

    const auto abs = bundle_root / rel.value();
    if (std::filesystem::is_symlink(abs, ec)) {
      if (!opts.security.allow_symlinks) {
        return Error::make(ErrorCode::PathUnsafe,
                           "symlinked inventory path rejected: " + rel.value());
      }
    }
    auto within = util::ensure_within_root(bundle_root, abs);
    if (!within) {
      return Error::make(ErrorCode::PathUnsafe,
                         "inventory path escapes bundle root (symlink escape or traversal): " +
                             rel.value());
    }
    if (!std::filesystem::is_regular_file(abs, ec)) {
      return Error::make(ErrorCode::ConfigInvalid, "missing inventoried file: " + rel.value());
    }

    util::FileSecurityPolicy file_policy = opts.security;
    file_policy.allowed_roots = {bundle_root};
    auto inspected = util::inspect_path(abs, file_policy);
    if (!inspected) {
      return inspected.error();
    }

    auto got = crypto::sha256_file_hex(abs);
    if (!got) {
      return got.error();
    }
    if (got.value() != sha) {
      return Error::make(ErrorCode::FileIntegrityFailed,
                         "inventory hash mismatch for " + rel.value(),
                         "Regenerate or restore the bundle artifact");
    }

    const auto size_bytes = entry.value("size_bytes", static_cast<std::uint64_t>(0));
    if (entry.contains("size_bytes") && size_bytes != inspected.value().size_bytes) {
      return Error::make(ErrorCode::FileIntegrityFailed,
                         "inventory size mismatch for " + rel.value());
    }

    BundleFileEntry fe;
    fe.relative_path = rel.value();
    fe.sha256_hex = sha;
    fe.size_bytes = inspected.value().size_bytes;
    fe.absolute_path = inspected.value().canonical_path;
    loaded.files.push_back(std::move(fe));
    declared.insert(rel.value());
  }

  if (opts.strict_inventory) {
    auto extras = collect_strict_extras(bundle_root, declared);
    if (!extras) {
      return extras.error();
    }
  }

  // Ensure each profile model path is inventoried.
  for (const auto& profile : loaded.profiles) {
    if (declared.count(profile.model_relative_path) == 0) {
      return Error::make(ErrorCode::FileIntegrityFailed,
                         "profile model path not present in inventory: " +
                             profile.model_relative_path);
    }
  }

  auto sig = verify_signature(bundle_root, opts, &loaded.signature);
  if (!sig) {
    return sig.error();
  }

  return loaded;
}

Result<nlohmann::json> verify_bundle_report(const std::filesystem::path& bundle_root,
                                            const BundleLoadOptions& options) {
  auto loaded = load_bundle(bundle_root, options);
  if (!loaded) {
    return loaded.error();
  }
  nlohmann::json report{
      {"ok", true},
      {"document_type", "perceptshift.bundle_verify"},
      {"schema_version", "1.0"},
      {"bundle_id", loaded.value().bundle_id},
      {"manifest_sha256", loaded.value().manifest_sha256_hex},
      {"files_checked", loaded.value().files.size()},
      {"profiles", loaded.value().profiles.size()},
      {"signature",
       {
           {"present", loaded.value().signature.present},
           {"verified", loaded.value().signature.verified},
           {"algorithm", loaded.value().signature.algorithm},
           {"key_id", loaded.value().signature.key_id},
           {"policy", to_string(options.signature_policy)},
       }},
      {"product_version", kVersionString},
  };
  return report;
}

} // namespace perceptshift::bundle
