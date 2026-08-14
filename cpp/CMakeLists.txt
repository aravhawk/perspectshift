set(PERCEPTSHIFT_CORE_SOURCES
  src/build_info.cpp
  src/crypto/digest.cpp
  src/crypto/signature.cpp
  src/crypto/verified_file.cpp
  src/util/file_security.cpp
  src/util/thread_affinity.cpp
  src/host/cpu_features.cpp
  src/host/cpu_topology.cpp
  src/host/memory_provider.cpp
  src/host/thermal_provider.cpp
  src/host/frequency_provider.cpp
  src/host/power_provider.cpp
  src/host/raspberry_pi_telemetry.cpp
  src/host/telemetry_snapshot.cpp
  src/host/host_fingerprint.cpp
  src/image/image_view.cpp
  src/image/tensor_buffer.cpp
  src/image/preprocess_config.cpp
  src/image/preprocessor_scalar.cpp
  src/image/preprocessor_neon.cpp
  src/image/preprocessor_dispatch.cpp
  src/inference/onnx_session.cpp
  src/inference/session_pool.cpp
  src/adapters/raw_tensor_adapter.cpp
  src/adapters/classification_adapter.cpp
  src/adapters/yolo_v8_adapter.cpp
  src/adapters/adapter_factory.cpp
  src/profiles/profile_registry.cpp
  src/bundle/bundle_loader.cpp
  src/runtime/latest_frame_queue.cpp
  src/runtime/latency_estimator.cpp
  src/runtime/eligibility.cpp
  src/runtime/health_machine.cpp
  src/runtime/controller.cpp
  src/runtime/policy_loader.cpp
  src/runtime/profile_executor.cpp
  src/runtime/runtime_engine.cpp
)

add_library(perceptshift_core ${PERCEPTSHIFT_CORE_SOURCES})
add_library(perceptshift::core ALIAS perceptshift_core)

target_include_directories(perceptshift_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_BINARY_DIR}/generated>
    $<INSTALL_INTERFACE:include>
)

target_link_libraries(perceptshift_core
  PUBLIC
    nlohmann_json::nlohmann_json
    spdlog::spdlog
    yaml-cpp
    OpenSSL::Crypto
    Threads::Threads
)

if(PERCEPTSHIFT_HAS_ONNXRUNTIME)
  target_compile_definitions(perceptshift_core PUBLIC PERCEPTSHIFT_HAS_ONNXRUNTIME=1)
  target_link_libraries(perceptshift_core PUBLIC onnxruntime::onnxruntime)
  message(STATUS "PerceptShift linked ONNX Runtime version record: ${PERCEPTSHIFT_ORT_VERSION_STRING}")
else()
  target_compile_definitions(perceptshift_core PUBLIC PERCEPTSHIFT_HAS_ONNXRUNTIME=0)
endif()

perceptshift_set_warnings(perceptshift_core)
perceptshift_enable_hardening(perceptshift_core)
perceptshift_enable_sanitizers(perceptshift_core)

add_executable(perceptshift-runtime apps/runtime_main.cpp)
target_link_libraries(perceptshift-runtime PRIVATE perceptshift_core CLI11::CLI11)
perceptshift_set_warnings(perceptshift-runtime)
perceptshift_enable_sanitizers(perceptshift-runtime)

add_executable(perceptshift-bench-worker apps/bench_worker_main.cpp)
target_link_libraries(perceptshift-bench-worker PRIVATE perceptshift_core CLI11::CLI11)
perceptshift_set_warnings(perceptshift-bench-worker)
perceptshift_enable_sanitizers(perceptshift-bench-worker)

add_executable(perceptshift-inspect-worker apps/inspect_worker_main.cpp)
target_link_libraries(perceptshift-inspect-worker PRIVATE perceptshift_core CLI11::CLI11)
perceptshift_set_warnings(perceptshift-inspect-worker)
perceptshift_enable_sanitizers(perceptshift-inspect-worker)

add_executable(perceptshift-preprocess-worker apps/preprocess_worker_main.cpp)
target_link_libraries(perceptshift-preprocess-worker PRIVATE perceptshift_core CLI11::CLI11)
perceptshift_set_warnings(perceptshift-preprocess-worker)
perceptshift_enable_sanitizers(perceptshift-preprocess-worker)

install(TARGETS perceptshift_core perceptshift-runtime perceptshift-bench-worker
                perceptshift-inspect-worker perceptshift-preprocess-worker
  RUNTIME DESTINATION bin
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  COMPONENT core)
install(DIRECTORY include/perceptshift DESTINATION include COMPONENT core)

# Embed ONNX Runtime shared libraries next to the product and set RPATH so the
# installed runtime does not depend on a developer cache path.
if(PERCEPTSHIFT_HAS_ONNXRUNTIME AND PERCEPTSHIFT_ORT_ROOT)
  file(GLOB PERCEPTSHIFT_ORT_LIBS
    "${PERCEPTSHIFT_ORT_ROOT}/lib/libonnxruntime.so*"
    "${PERCEPTSHIFT_ORT_ROOT}/lib/libonnxruntime.dylib*"
    "${PERCEPTSHIFT_ORT_ROOT}/lib/libonnxruntime.*.dylib"
    "${PERCEPTSHIFT_ORT_ROOT}/lib/libonnxruntime_providers_shared.so*"
  )
  if(PERCEPTSHIFT_ORT_LIBS)
    install(FILES ${PERCEPTSHIFT_ORT_LIBS}
      DESTINATION lib/perceptshift
      COMPONENT core
    )
  endif()
  foreach(_ps_bin perceptshift-runtime perceptshift-bench-worker perceptshift-inspect-worker
                  perceptshift-preprocess-worker)
    set_target_properties(${_ps_bin} PROPERTIES
      INSTALL_RPATH "\$ORIGIN/../lib/perceptshift"
      BUILD_RPATH "${PERCEPTSHIFT_ORT_ROOT}/lib"
      BUILD_WITH_INSTALL_RPATH OFF
    )
    if(UNIX AND NOT APPLE)
      target_link_options(${_ps_bin} PRIVATE "-Wl,-rpath,${PERCEPTSHIFT_ORT_ROOT}/lib")
    endif()
  endforeach()
endif()
