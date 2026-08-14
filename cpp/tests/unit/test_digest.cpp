#include "perceptshift/crypto/digest.hpp"

#include <gtest/gtest.h>

TEST(DigestTest, KnownVector) {
  auto d = perceptshift::crypto::sha256_bytes(std::string_view("abc"));
  ASSERT_TRUE(d.ok());
  EXPECT_EQ(perceptshift::crypto::to_hex(d.value()),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}

TEST(DigestTest, HexRoundTrip) {
  auto d = perceptshift::crypto::sha256_bytes(std::string_view("perceptshift"));
  ASSERT_TRUE(d.ok());
  const auto hex = perceptshift::crypto::to_hex(d.value());
  auto back = perceptshift::crypto::from_hex(hex);
  ASSERT_TRUE(back.ok());
  EXPECT_EQ(d.value(), back.value());
}
