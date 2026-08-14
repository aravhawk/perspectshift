#include "perceptshift/bundle/bundle_loader.hpp"
#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/crypto/signature.hpp"

#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>
#include <iomanip>
#include <openssl/evp.h>
#include <sstream>

namespace {

std::string to_hex_bytes(const std::vector<std::uint8_t>& bytes) {
  std::ostringstream oss;
  oss << std::hex << std::setfill('0');
  for (auto b : bytes) {
    oss << std::setw(2) << static_cast<unsigned>(b);
  }
  return oss.str();
}

std::filesystem::path write_minimal_bundle(const std::filesystem::path& root) {
  std::filesystem::create_directories(root / "models");
  std::filesystem::create_directories(root / "profiles");
  {
    std::ofstream out(root / "models" / "m.onnx", std::ios::binary);
    out << "fake-onnx";
  }
  const auto model_sha = perceptshift::crypto::sha256_file_hex(root / "models" / "m.onnx");
  nlohmann::json profile{
      {"profile_id", "p1"},
      {"label", "p1"},
      {"model_sha256", model_sha.value()},
      {"model_relative_path", "models/m.onnx"},
      {"status", "certified"},
      {"session",
       {{"provider_order", nlohmann::json::array({"CPUExecutionProvider"})},
        {"intra_op_threads", 1}}},
      {"adapter", {{"name", "raw_tensor"}}},
      {"preprocess", {{"backend", "scalar"}}},
      {"certified_p99_ms", 10.0},
      {"certified_quality", 1.0},
      {"offline_envelope_ms", 10.0},
  };
  {
    std::ofstream out(root / "profiles" / "p1.json");
    out << profile.dump(2);
  }
  const auto profile_sha = perceptshift::crypto::sha256_file_hex(root / "profiles" / "p1.json");
  const auto model_size = std::filesystem::file_size(root / "models" / "m.onnx");
  const auto profile_size = std::filesystem::file_size(root / "profiles" / "p1.json");
  nlohmann::json manifest{
      {"schema_version", "1.0"},
      {"document_type", "perceptshift.profile_bundle"},
      {"bundle_id", "test-bundle"},
      {"product_version", "0.1.0"},
      {"minimum_compatible_runtime_version", "0.1.0"},
      {"created_at", "2026-01-01T00:00:00Z"},
      {"producer", {{"name", "test"}, {"version", "0.1.0"}}},
      {"adapter", {{"name", "raw_tensor"}}},
      {"quality_metric_name", "n/a"},
      {"quality_direction", "higher_is_better"},
      {"profiles", nlohmann::json::array({profile})},
      {"files",
       nlohmann::json::array({
           {{"path", "models/m.onnx"}, {"sha256", model_sha.value()}, {"size_bytes", model_size}},
           {{"path", "profiles/p1.json"},
            {"sha256", profile_sha.value()},
            {"size_bytes", profile_size}},
       })},
  };
  {
    std::ofstream out(root / "manifest.json");
    out << manifest.dump(2);
  }
  const auto man_sha = perceptshift::crypto::sha256_file_hex(root / "manifest.json");
  {
    std::ofstream out(root / "manifest.sha256");
    out << man_sha.value() << "\n";
  }
  return root;
}

} // namespace

TEST(BundleLoaderTest, RejectsPathTraversal) {
  const auto root = std::filesystem::temp_directory_path() / "ps-bundle-trav";
  std::filesystem::remove_all(root);
  write_minimal_bundle(root);
  auto manifest = nlohmann::json::parse(std::ifstream(root / "manifest.json"));
  manifest["files"].push_back(
      {{"path", "../escape.bin"}, {"sha256", std::string(64, 'a')}, {"size_bytes", 1}});
  {
    std::ofstream out(root / "manifest.json");
    out << manifest.dump(2);
  }
  const auto man_sha = perceptshift::crypto::sha256_file_hex(root / "manifest.json");
  {
    std::ofstream out(root / "manifest.sha256");
    out << man_sha.value() << "\n";
  }
  perceptshift::bundle::BundleLoadOptions opts;
  opts.signature_policy = perceptshift::bundle::SignaturePolicy::Disabled;
  auto loaded = perceptshift::bundle::load_bundle(root, opts);
  ASSERT_FALSE(loaded.ok());
  EXPECT_EQ(loaded.error().code, perceptshift::ErrorCode::PathUnsafe);
  std::filesystem::remove_all(root);
}

TEST(BundleLoaderTest, LoadsValidBundleWithoutSignature) {
  const auto root = std::filesystem::temp_directory_path() / "ps-bundle-ok";
  std::filesystem::remove_all(root);
  write_minimal_bundle(root);
  perceptshift::bundle::BundleLoadOptions opts;
  opts.signature_policy = perceptshift::bundle::SignaturePolicy::Disabled;
  auto loaded = perceptshift::bundle::load_bundle(root, opts);
  ASSERT_TRUE(loaded.ok()) << loaded.error().message;
  EXPECT_EQ(loaded.value().bundle_id, "test-bundle");
  EXPECT_EQ(loaded.value().profiles.size(), 1u);
  std::filesystem::remove_all(root);
}

TEST(BundleLoaderTest, Ed25519RoundTrip) {
  const auto root = std::filesystem::temp_directory_path() / "ps-bundle-sig";
  std::filesystem::remove_all(root);
  write_minimal_bundle(root);

  std::vector<std::uint8_t> seed(32, 7);
  const auto digest_path = root / "manifest.sha256";
  std::ifstream din(digest_path, std::ios::binary);
  std::string payload((std::istreambuf_iterator<char>(din)), std::istreambuf_iterator<char>());
  auto sig = perceptshift::crypto::ed25519_sign(
      seed, reinterpret_cast<const std::uint8_t*>(payload.data()), payload.size());
  ASSERT_TRUE(sig.ok());

  EVP_PKEY* pkey =
      EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, nullptr, seed.data(), seed.size());
  ASSERT_NE(pkey, nullptr);
  std::vector<std::uint8_t> pubkey(32);
  std::size_t len = 32;
  ASSERT_EQ(EVP_PKEY_get_raw_public_key(pkey, pubkey.data(), &len), 1);
  EVP_PKEY_free(pkey);

  nlohmann::json meta{
      {"algorithm", "ed25519"},
      {"key_id", "test"},
      {"payload_schema_version", "1.0"},
      {"encoding", "hex"},
      {"signature", to_hex_bytes(sig.value())},
  };
  {
    std::ofstream out(root / "manifest.sig");
    out << meta.dump(2);
  }

  perceptshift::bundle::BundleLoadOptions opts;
  opts.signature_policy = perceptshift::bundle::SignaturePolicy::Required;
  opts.verify_public_key = pubkey;
  auto loaded = perceptshift::bundle::load_bundle(root, opts);
  ASSERT_TRUE(loaded.ok()) << loaded.error().message;
  EXPECT_TRUE(loaded.value().signature.verified);
  std::filesystem::remove_all(root);
}
