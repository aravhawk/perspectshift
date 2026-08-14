#include "perceptshift/host/cpu_features.hpp"

#if defined(__linux__) && defined(__aarch64__)
#include <asm/hwcap.h>
#include <sys/auxv.h>
#endif

#if defined(__APPLE__)
#include <sys/sysctl.h>
#endif

namespace perceptshift::host {

CpuFeatures detect_cpu_features() {
  CpuFeatures f;
#if defined(__aarch64__) || defined(__arm64__)
  f.architecture = "aarch64";
#elif defined(__x86_64__)
  f.architecture = "x86_64";
#else
  f.architecture = "unknown";
#endif

#if defined(__linux__) && defined(__aarch64__)
  const unsigned long hwcap = getauxval(AT_HWCAP);
  const unsigned long hwcap2 = getauxval(AT_HWCAP2);
  f.fp = (hwcap & HWCAP_FP) != 0;
  f.asimd = (hwcap & HWCAP_ASIMD) != 0;
  f.aes = (hwcap & HWCAP_AES) != 0;
  f.crc32 = (hwcap & HWCAP_CRC32) != 0;
  f.atomics = (hwcap & HWCAP_ATOMICS) != 0;
#ifdef HWCAP_FPHP
  f.fp16 = (hwcap & HWCAP_FPHP) != 0;
#endif
#ifdef HWCAP_ASIMDDP
  f.dotprod = (hwcap & HWCAP_ASIMDDP) != 0;
#endif
#ifdef HWCAP_SVE
  f.sve = (hwcap & HWCAP_SVE) != 0;
#endif
#ifdef HWCAP2_SVE2
  f.sve2 = (hwcap2 & HWCAP2_SVE2) != 0;
#endif
#ifdef HWCAP2_I8MM
  f.i8mm = (hwcap2 & HWCAP2_I8MM) != 0;
#endif
#ifdef HWCAP2_BF16
  f.bf16 = (hwcap2 & HWCAP2_BF16) != 0;
#endif
#elif defined(__APPLE__) && (defined(__aarch64__) || defined(__arm64__))
  f.fp = true;
  f.asimd = true;
  f.aes = true;
  f.crc32 = true;
  f.atomics = true;
  int val = 0;
  size_t size = sizeof(val);
  if (sysctlbyname("hw.optional.arm.FEAT_DotProd", &val, &size, nullptr, 0) == 0) {
    f.dotprod = val != 0;
  }
  size = sizeof(val);
  if (sysctlbyname("hw.optional.arm.FEAT_FP16", &val, &size, nullptr, 0) == 0) {
    f.fp16 = val != 0;
  }
#else
  f.unavailable_reason_codes.push_back("CPU_FEATURES_PARTIAL_OR_UNAVAILABLE");
#endif
  return f;
}

} // namespace perceptshift::host
