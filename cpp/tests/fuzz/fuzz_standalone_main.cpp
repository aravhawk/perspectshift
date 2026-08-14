// Standalone corpus driver used when libFuzzer is unavailable (e.g. Apple CLT).
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size);

namespace {

[[nodiscard]] int run_one(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return 1;
  }
  std::vector<uint8_t> buf((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  LLVMFuzzerTestOneInput(buf.data(), buf.size());
  return 0;
}

[[nodiscard]] int run_directory(const std::filesystem::path& dir, int max_iters) {
  int n = 0;
  for (const auto& ent : std::filesystem::recursive_directory_iterator(dir)) {
    if (!ent.is_regular_file()) {
      continue;
    }
    if (run_one(ent.path()) != 0) {
      return 1;
    }
    ++n;
    if (max_iters > 0 && n >= max_iters) {
      break;
    }
  }
  return 0;
}

[[nodiscard]] int mutate_smoke(const std::vector<uint8_t>& seed, int seconds) {
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::seconds(std::max(1, seconds));
  std::vector<uint8_t> buf = seed;
  std::uint64_t x = 0x9e3779b97f4a7c15ULL ^ (seed.empty() ? 1ULL : seed[0]);
  int iters = 0;
  while (std::chrono::steady_clock::now() < deadline) {
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    if (buf.empty()) {
      buf.push_back(static_cast<uint8_t>(x));
    } else {
      buf[static_cast<std::size_t>(x % buf.size())] ^= static_cast<uint8_t>(x);
      if ((x & 7U) == 0U && buf.size() < 4096) {
        buf.push_back(static_cast<uint8_t>(x >> 8));
      }
      if ((x & 15U) == 0U && buf.size() > 1) {
        buf.pop_back();
      }
    }
    LLVMFuzzerTestOneInput(buf.data(), buf.size());
    ++iters;
  }
  std::cerr << "standalone_fuzz_iters=" << iters << "\n";
  return 0;
}

} // namespace

int main(int argc, char** argv) {
  int seconds = 5;
  std::vector<std::string> paths;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg.rfind("-max_total_time=", 0) == 0) {
      seconds = std::atoi(arg.c_str() + std::strlen("-max_total_time="));
      continue;
    }
    if (arg.rfind("-artifact_prefix=", 0) == 0) {
      continue;
    }
    if (!arg.empty() && arg[0] == '-') {
      continue;
    }
    paths.push_back(arg);
  }

  if (!paths.empty()) {
    for (const auto& p : paths) {
      std::error_code ec;
      if (std::filesystem::is_directory(p, ec)) {
        if (run_directory(p, 0) != 0) {
          return 1;
        }
      } else if (run_one(p) != 0) {
        return 1;
      }
    }
  }

  static const uint8_t kSeed[] = {'{', '"', 'a', '"', ':', '1', '}'};
  return mutate_smoke(std::vector<uint8_t>(kSeed, kSeed + sizeof(kSeed)), seconds);
}
