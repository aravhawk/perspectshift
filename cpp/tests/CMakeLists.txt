include(GoogleTest)

add_executable(perceptshift_core_tests
  unit/test_result.cpp
  unit/test_digest.cpp
  unit/test_preprocessor.cpp
  unit/test_adapters.cpp
  unit/test_controller.cpp
  unit/test_latest_frame_queue.cpp
  unit/test_bundle_loader.cpp
  unit/test_runtime_engine.cpp
  unit/test_policy_loader.cpp
  unit/test_profile_executor_image.cpp
)

target_link_libraries(perceptshift_core_tests
  PRIVATE
    perceptshift_core
    GTest::gtest_main
)

perceptshift_set_warnings(perceptshift_core_tests)
perceptshift_enable_sanitizers(perceptshift_core_tests)

include(GoogleTest)
gtest_discover_tests(perceptshift_core_tests)

# --- Fuzz targets -----------------------------------------------------------
# Prefer libFuzzer when the toolchain provides it; otherwise link a portable
# standalone corpus/mutation driver so smoke gates remain fail-closed.
# Apple Command Line Tools typically lack libclang_rt.fuzzer_osx.a.
set(PERCEPTSHIFT_HAS_LIBFUZZER FALSE)
if(NOT APPLE AND CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  include(CheckCXXSourceCompiles)
  set(CMAKE_REQUIRED_FLAGS "-fsanitize=fuzzer")
  set(CMAKE_REQUIRED_LINK_OPTIONS "-fsanitize=fuzzer")
  check_cxx_source_compiles("
#include <stdint.h>
#include <stddef.h>
extern \"C\" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
  (void)Data; (void)Size; return 0;
}
" PERCEPTSHIFT_HAS_LIBFUZZER)
  unset(CMAKE_REQUIRED_FLAGS)
  unset(CMAKE_REQUIRED_LINK_OPTIONS)
endif()
if(PERCEPTSHIFT_HAS_LIBFUZZER)
  message(STATUS "Fuzz targets: libFuzzer")
else()
  message(STATUS "Fuzz targets: standalone driver (libFuzzer unavailable)")
endif()

function(perceptshift_add_fuzz name source)
  add_executable(${name} ${source})
  target_link_libraries(${name} PRIVATE perceptshift_core)
  perceptshift_set_warnings(${name})
  perceptshift_enable_sanitizers(${name})
  if(PERCEPTSHIFT_HAS_LIBFUZZER)
    target_compile_options(${name} PRIVATE -fsanitize=fuzzer)
    target_link_options(${name} PRIVATE -fsanitize=fuzzer)
  else()
    target_sources(${name} PRIVATE fuzz/fuzz_standalone_main.cpp)
  endif()
endfunction()

perceptshift_add_fuzz(fuzz_signature_policy fuzz/fuzz_signature_policy.cpp)
perceptshift_add_fuzz(fuzz_digest_hex fuzz/fuzz_digest_hex.cpp)
perceptshift_add_fuzz(fuzz_runtime_policy_json fuzz/fuzz_runtime_policy_json.cpp)
perceptshift_add_fuzz(fuzz_path_security fuzz/fuzz_path_security.cpp)
