include(FetchContent)

find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

FetchContent_Declare(
  nlohmann_json
  URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
  URL_HASH SHA256=d6c65aca6b1ed68e7a182f4757257b107ae403032760ed6ef121c9d55e81757d
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)

FetchContent_Declare(
  spdlog
  URL https://github.com/gabime/spdlog/archive/refs/tags/v1.14.1.tar.gz
  URL_HASH SHA256=1586508029a7d0670dfcb2d97575dcdc242d3868a259742b69f100801ab4e16b
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)

FetchContent_Declare(
  yaml-cpp
  URL https://github.com/jbeder/yaml-cpp/archive/refs/tags/0.8.0.tar.gz
  URL_HASH SHA256=fbe74bbdcee21d656715688706da3c8becfd946d92cd44705cc6098bb23b3a16
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)

FetchContent_Declare(
  cli11
  URL https://github.com/CLIUtils/CLI11/archive/refs/tags/v2.4.2.tar.gz
  URL_HASH SHA256=f2d893a65c3b1324c50d4e682c0cdc021dd0477ae2c048544f39eed6654b699a
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)

set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(SPDLOG_BUILD_EXAMPLE OFF CACHE BOOL "" FORCE)
set(CLI11_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(CLI11_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
# yaml-cpp 0.8.0 still declares an old cmake_minimum_required; allow configure on CMake 4+.
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "" FORCE)

FetchContent_MakeAvailable(nlohmann_json spdlog yaml-cpp cli11)

if(PERCEPTSHIFT_BUILD_TESTS)
  FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.15.2.tar.gz
    URL_HASH SHA256=7b42b4d6ed48810c5362c265a17faebe90dc2373c885e5216439d37927f02926
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
  )
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  set(BUILD_GMOCK ON CACHE BOOL "" FORCE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)
endif()

# ONNX Runtime discovery contract:
#   PERCEPTSHIFT_ORT_ROOT (preferred) or ORT_PREFIX / ENV{PERCEPTSHIFT_ORT_ROOT} / ENV{ORT_PREFIX}
# Product pin: 1.28.0 (must align with Python onnxruntime==1.28.0)
set(PERCEPTSHIFT_ORT_PINNED_VERSION "1.28.0")
set(PERCEPTSHIFT_ORT_VERSION_STRING "unavailable")
set(PERCEPTSHIFT_HAS_ONNXRUNTIME OFF)

if(PERCEPTSHIFT_WITH_ONNXRUNTIME)
  if(NOT PERCEPTSHIFT_ORT_ROOT AND DEFINED ENV{PERCEPTSHIFT_ORT_ROOT})
    set(PERCEPTSHIFT_ORT_ROOT "$ENV{PERCEPTSHIFT_ORT_ROOT}")
  endif()
  if(NOT PERCEPTSHIFT_ORT_ROOT AND DEFINED ENV{ORT_PREFIX})
    set(PERCEPTSHIFT_ORT_ROOT "$ENV{ORT_PREFIX}")
  endif()
  if(NOT PERCEPTSHIFT_ORT_ROOT AND ORT_PREFIX)
    set(PERCEPTSHIFT_ORT_ROOT "${ORT_PREFIX}")
  endif()
  # Default local cache used by scripts/build-onnxruntime.sh and prebuilt downloads.
  if(NOT PERCEPTSHIFT_ORT_ROOT AND EXISTS "${CMAKE_SOURCE_DIR}/.cache/onnxruntime/include/onnxruntime_cxx_api.h")
    set(PERCEPTSHIFT_ORT_ROOT "${CMAKE_SOURCE_DIR}/.cache/onnxruntime")
  endif()

  if(PERCEPTSHIFT_ORT_ROOT)
    set(ONNXRUNTIME_INCLUDE_DIR "${PERCEPTSHIFT_ORT_ROOT}/include")
    find_library(ONNXRUNTIME_LIBRARY
      NAMES onnxruntime
      PATHS "${PERCEPTSHIFT_ORT_ROOT}/lib" "${PERCEPTSHIFT_ORT_ROOT}/lib64"
      NO_DEFAULT_PATH
    )
  else()
    find_path(ONNXRUNTIME_INCLUDE_DIR onnxruntime_cxx_api.h
      PATHS /usr/include /usr/local/include /opt/homebrew/include
      PATH_SUFFIXES onnxruntime
    )
    find_library(ONNXRUNTIME_LIBRARY NAMES onnxruntime)
  endif()

  if(ONNXRUNTIME_INCLUDE_DIR AND ONNXRUNTIME_LIBRARY)
    set(PERCEPTSHIFT_HAS_ONNXRUNTIME ON)
    add_library(onnxruntime::onnxruntime UNKNOWN IMPORTED)
    set_target_properties(onnxruntime::onnxruntime PROPERTIES
      IMPORTED_LOCATION "${ONNXRUNTIME_LIBRARY}"
      INTERFACE_INCLUDE_DIRECTORIES "${ONNXRUNTIME_INCLUDE_DIR}"
    )
    if(EXISTS "${PERCEPTSHIFT_ORT_ROOT}/VERSION.txt")
      file(READ "${PERCEPTSHIFT_ORT_ROOT}/VERSION.txt" PERCEPTSHIFT_ORT_VERSION_STRING)
      string(STRIP "${PERCEPTSHIFT_ORT_VERSION_STRING}" PERCEPTSHIFT_ORT_VERSION_STRING)
    elseif(EXISTS "${PERCEPTSHIFT_ORT_ROOT}/VERSION_NUMBER")
      file(READ "${PERCEPTSHIFT_ORT_ROOT}/VERSION_NUMBER" PERCEPTSHIFT_ORT_VERSION_STRING)
      string(STRIP "${PERCEPTSHIFT_ORT_VERSION_STRING}" PERCEPTSHIFT_ORT_VERSION_STRING)
    else()
      set(PERCEPTSHIFT_ORT_VERSION_STRING "detected")
    endif()
    message(STATUS "ONNX Runtime found: ${ONNXRUNTIME_LIBRARY}")
    message(STATUS "ONNX Runtime version: ${PERCEPTSHIFT_ORT_VERSION_STRING} (pinned ${PERCEPTSHIFT_ORT_PINNED_VERSION})")
    if(PERCEPTSHIFT_ORT_ROOT)
      list(APPEND CMAKE_BUILD_RPATH "${PERCEPTSHIFT_ORT_ROOT}/lib")
    endif()
    if(NOT PERCEPTSHIFT_ORT_VERSION_STRING STREQUAL "detected" AND
       NOT PERCEPTSHIFT_ORT_VERSION_STRING STREQUAL PERCEPTSHIFT_ORT_PINNED_VERSION)
      message(WARNING "ONNX Runtime version ${PERCEPTSHIFT_ORT_VERSION_STRING} differs from pin ${PERCEPTSHIFT_ORT_PINNED_VERSION}")
    endif()
  else()
    message(FATAL_ERROR
      "PERCEPTSHIFT_WITH_ONNXRUNTIME=ON but ONNX Runtime headers/library were not found. "
      "Set PERCEPTSHIFT_ORT_ROOT (or ORT_PREFIX) to an install of onnxruntime ${PERCEPTSHIFT_ORT_PINNED_VERSION}, "
      "or use the no-ort preset for utility-only builds. "
      "Example: export PERCEPTSHIFT_ORT_ROOT=${CMAKE_SOURCE_DIR}/.cache/onnxruntime")
  endif()
else()
  message(STATUS "Building without ONNX Runtime (PERCEPTSHIFT_WITH_ONNXRUNTIME=OFF)")
endif()
