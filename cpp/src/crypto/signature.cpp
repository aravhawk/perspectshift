#include "perceptshift/crypto/signature.hpp"

#include <openssl/evp.h>

namespace perceptshift::crypto {

Result<std::vector<std::uint8_t>> ed25519_sign(const std::vector<std::uint8_t>& private_key_32,
                                               const std::uint8_t* message,
                                               std::size_t message_len) {
  if (private_key_32.size() != 32) {
    return Error::make(ErrorCode::ConfigInvalid, "Ed25519 private key must be 32 bytes");
  }
  EVP_PKEY* pkey = EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, nullptr, private_key_32.data(),
                                                private_key_32.size());
  if (pkey == nullptr) {
    return Error::make(ErrorCode::InternalInvariantFailed, "failed to load Ed25519 private key");
  }
  EVP_MD_CTX* ctx = EVP_MD_CTX_new();
  if (ctx == nullptr) {
    EVP_PKEY_free(pkey);
    return Error::make(ErrorCode::InternalInvariantFailed, "EVP_MD_CTX_new failed");
  }
  if (EVP_DigestSignInit(ctx, nullptr, nullptr, nullptr, pkey) != 1) {
    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return Error::make(ErrorCode::InternalInvariantFailed, "Ed25519 sign init failed");
  }
  std::size_t sig_len = 0;
  if (EVP_DigestSign(ctx, nullptr, &sig_len, message, message_len) != 1) {
    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return Error::make(ErrorCode::InternalInvariantFailed, "Ed25519 sign size failed");
  }
  std::vector<std::uint8_t> sig(sig_len);
  if (EVP_DigestSign(ctx, sig.data(), &sig_len, message, message_len) != 1) {
    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return Error::make(ErrorCode::InternalInvariantFailed, "Ed25519 sign failed");
  }
  sig.resize(sig_len);
  EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(pkey);
  return sig;
}

Result<void> ed25519_verify(const std::vector<std::uint8_t>& public_key_32,
                            const std::uint8_t* message, std::size_t message_len,
                            const std::vector<std::uint8_t>& signature_64) {
  if (public_key_32.size() != 32) {
    return Error::make(ErrorCode::ConfigInvalid, "Ed25519 public key must be 32 bytes");
  }
  if (signature_64.size() != 64) {
    return Error::make(ErrorCode::SignatureInvalid, "Ed25519 signature must be 64 bytes");
  }
  EVP_PKEY* pkey = EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, nullptr, public_key_32.data(),
                                               public_key_32.size());
  if (pkey == nullptr) {
    return Error::make(ErrorCode::SignatureInvalid, "failed to load Ed25519 public key");
  }
  EVP_MD_CTX* ctx = EVP_MD_CTX_new();
  if (ctx == nullptr) {
    EVP_PKEY_free(pkey);
    return Error::make(ErrorCode::InternalInvariantFailed, "EVP_MD_CTX_new failed");
  }
  if (EVP_DigestVerifyInit(ctx, nullptr, nullptr, nullptr, pkey) != 1) {
    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return Error::make(ErrorCode::InternalInvariantFailed, "Ed25519 verify init failed");
  }
  const int rc =
      EVP_DigestVerify(ctx, signature_64.data(), signature_64.size(), message, message_len);
  EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(pkey);
  if (rc != 1) {
    return Error::make(ErrorCode::SignatureInvalid, "Ed25519 signature verification failed",
                       "Ensure the correct public key and untampered payload");
  }
  return Result<void>::success();
}

} // namespace perceptshift::crypto
