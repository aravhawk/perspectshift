cmake_minimum_required(VERSION 3.22)
project(perceptshift_ros)

option(PERCEPTSHIFT_WARNINGS_AS_ERRORS "Treat project-owned compiler warnings as errors" OFF)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
  if(PERCEPTSHIFT_WARNINGS_AS_ERRORS)
    add_compile_options(
      -Werror=deprecated-declarations
      -Werror=return-type
      -Werror=init-self
    )
  endif()
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(lifecycle_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(diagnostic_updater REQUIRED)
find_package(perceptshift_msgs REQUIRED)
find_package(image_transport REQUIRED)

add_library(perceptshift_ros_component SHARED
  src/runtime_node.cpp
  src/diagnostics_publisher.cpp
  src/image_intake.cpp
  src/trace_hooks.cpp
)

target_include_directories(perceptshift_ros_component PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(perceptshift_ros_component
  rclcpp
  rclcpp_lifecycle
  rclcpp_components
  lifecycle_msgs
  sensor_msgs
  std_msgs
  diagnostic_msgs
  diagnostic_updater
  perceptshift_msgs
  image_transport
)

# Production runtime requires libperceptshift_core. Prefer colocated source tree.
set(PERCEPTSHIFT_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../..")
if(TARGET perceptshift_core)
  set(PERCEPTSHIFT_CORE_TARGET perceptshift_core)
else()
  find_library(PERCEPTSHIFT_CORE_LIB
    NAMES perceptshift_core
    PATHS
      /opt/perceptshift/lib
      /usr/lib
      "${PERCEPTSHIFT_REPO_ROOT}/build/deb-release/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/noble-arm64/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/ros-core/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/default/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/dev-arm64/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/dev-x64/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/release-arm64/cpp"
      "${PERCEPTSHIFT_REPO_ROOT}/build/release-x64/cpp"
      "$ENV{PERCEPTSHIFT_PREFIX}/lib"
      "${PERCEPTSHIFT_REPO_ROOT}/build"
  )
  find_path(PERCEPTSHIFT_CORE_INCLUDE
    NAMES perceptshift/runtime/runtime_engine.hpp
    PATHS
      /opt/perceptshift/include
      /usr/include
      "${PERCEPTSHIFT_REPO_ROOT}/cpp/include"
  )
  find_path(PERCEPTSHIFT_NLOHMANN_INCLUDE
    NAMES nlohmann/json.hpp
    PATHS
      /usr/include
      "${PERCEPTSHIFT_REPO_ROOT}/build/deb-release/_deps/nlohmann_json-src/include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/deb-release/_deps/nlohmann_json-src/single_include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/ros-core/_deps/nlohmann_json-src/include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/ros-core/_deps/nlohmann_json-src/single_include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/release-x64/_deps/nlohmann_json-src/include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/noble-arm64/_deps/nlohmann_json-src/include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/default/_deps/nlohmann_json-src/include"
      "${PERCEPTSHIFT_REPO_ROOT}/build/clean/_deps/nlohmann_json-src/include"
  )
endif()

if(NOT PERCEPTSHIFT_CORE_TARGET AND NOT (PERCEPTSHIFT_CORE_LIB AND PERCEPTSHIFT_CORE_INCLUDE))
  message(FATAL_ERROR
    "libperceptshift_core is required for perceptshift_ros runtime. "
    "Build the native core first (cmake --preset default && cmake --build --preset default). "
    "A transport-only conceptual core boundary is not permitted for the installed runtime package.")
endif()

find_package(OpenSSL REQUIRED)
find_library(PERCEPTSHIFT_ONNXRUNTIME_LIB
  NAMES onnxruntime
  PATHS
    /opt/perceptshift/lib
    "$ENV{PERCEPTSHIFT_ORT_ROOT}/lib"
    "${PERCEPTSHIFT_REPO_ROOT}/.cache/onnxruntime-linux-aarch64-1.28.0/lib"
    "${PERCEPTSHIFT_REPO_ROOT}/.cache/onnxruntime-linux-x64-1.28.0/lib"
    "${PERCEPTSHIFT_REPO_ROOT}/.cache/onnxruntime/lib"
)

if(PERCEPTSHIFT_CORE_TARGET)
  target_link_libraries(perceptshift_ros_component PUBLIC ${PERCEPTSHIFT_CORE_TARGET})
else()
  # Use plain signatures to stay compatible with ament_target_dependencies.
  target_include_directories(perceptshift_ros_component
    PUBLIC ${PERCEPTSHIFT_CORE_INCLUDE} ${PERCEPTSHIFT_NLOHMANN_INCLUDE})
  if(NOT PERCEPTSHIFT_NLOHMANN_INCLUDE)
    message(FATAL_ERROR "nlohmann/json.hpp required to compile against libperceptshift_core headers")
  endif()
  if(NOT PERCEPTSHIFT_ONNXRUNTIME_LIB)
    message(FATAL_ERROR "libonnxruntime required to link perceptshift_ros against ORT-enabled core")
  endif()
  target_link_libraries(perceptshift_ros_component
    ${PERCEPTSHIFT_CORE_LIB}
    OpenSSL::Crypto
    ${PERCEPTSHIFT_ONNXRUNTIME_LIB}
  )
endif()
target_compile_definitions(perceptshift_ros_component PRIVATE PERCEPTSHIFT_HAS_CORE=1)

rclcpp_components_register_nodes(perceptshift_ros_component
  "perceptshift_ros::RuntimeNode"
)

add_executable(perceptshift_runtime_node src/runtime_main.cpp)
target_link_libraries(perceptshift_runtime_node perceptshift_ros_component)
ament_target_dependencies(perceptshift_runtime_node
  rclcpp
  rclcpp_lifecycle
)

install(TARGETS perceptshift_ros_component
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS perceptshift_runtime_node
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

install(FILES perceptshift_components.xml
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  # Style linters are enforced via repo clang-format/ruff; do not gate ROS build
  # on ament_lint_common (cpplint/uncrustify) which conflicts with project style.

  ament_add_gtest(test_image_intake test/test_image_intake.cpp)
  if(TARGET test_image_intake)
    target_link_libraries(test_image_intake perceptshift_ros_component)
  endif()

  ament_add_gtest(test_lifecycle_params test/test_lifecycle_params.cpp)
  if(TARGET test_lifecycle_params)
    target_link_libraries(test_lifecycle_params perceptshift_ros_component)
  endif()
endif()

ament_package()
