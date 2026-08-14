cmake_minimum_required(VERSION 3.28)

file(READ "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" PERCEPTSHIFT_VERSION_RAW)
string(STRIP "${PERCEPTSHIFT_VERSION_RAW}" PERCEPTSHIFT_VERSION)

project(perceptshift
  VERSION ${PERCEPTSHIFT_VERSION}
  DESCRIPTION "Deadline-aware adaptive ONNX Runtime inference for Arm64 ROS 2"
  LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
# Required so libperceptshift_core.a can link into ROS shared components.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(PERCEPTSHIFT_BUILD_TESTS "Build C++ tests" ON)
option(PERCEPTSHIFT_BUILD_BENCHMARKS "Build microbenchmarks" OFF)
option(PERCEPTSHIFT_ENABLE_ASAN "Enable AddressSanitizer" OFF)
option(PERCEPTSHIFT_ENABLE_UBSAN "Enable UndefinedBehaviorSanitizer" OFF)
option(PERCEPTSHIFT_ENABLE_TSAN "Enable ThreadSanitizer" OFF)
option(PERCEPTSHIFT_ENABLE_COVERAGE "Enable gcov/lcov coverage flags" OFF)
option(PERCEPTSHIFT_WITH_ONNXRUNTIME "Build with ONNX Runtime" ON)
option(PERCEPTSHIFT_WARNINGS_AS_ERRORS "Treat project-owned compiler warnings as errors" OFF)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

include(Version)
include(CompilerWarnings)
include(Hardening)
include(Sanitizers)
include(Dependencies)

add_subdirectory(cpp)

if(PERCEPTSHIFT_BUILD_TESTS)
  enable_testing()
  add_subdirectory(cpp/tests)
endif()

# --- Install layout (monolithic Debian package preferred for v1) -------------
include(GNUInstallDirs)

install(DIRECTORY "${CMAKE_SOURCE_DIR}/docs/"
  DESTINATION "${CMAKE_INSTALL_DOCDIR}"
  COMPONENT core
  FILES_MATCHING
    PATTERN "*.md"
    PATTERN "*.rst"
)
install(FILES
  "${CMAKE_SOURCE_DIR}/README.md"
  "${CMAKE_SOURCE_DIR}/LICENSE"
  "${CMAKE_SOURCE_DIR}/NOTICE"
  "${CMAKE_SOURCE_DIR}/CHANGELOG.md"
  DESTINATION "${CMAKE_INSTALL_DOCDIR}"
  COMPONENT core
)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/config/schemas"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/config"
  COMPONENT core
)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/config/templates"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/config"
  COMPONENT core
)
install(FILES
  "${CMAKE_SOURCE_DIR}/deploy/systemd/perceptshift-runtime.service"
  "${CMAKE_SOURCE_DIR}/deploy/systemd/perceptshift-api.service"
  DESTINATION "lib/systemd/system"
  COMPONENT core
)
install(FILES
  "${CMAKE_SOURCE_DIR}/deploy/sysusers.d/perceptshift.conf"
  DESTINATION "lib/sysusers.d"
  COMPONENT core
)
install(FILES
  "${CMAKE_SOURCE_DIR}/deploy/tmpfiles.d/perceptshift.conf"
  DESTINATION "lib/tmpfiles.d"
  COMPONENT core
)
install(PROGRAMS
  "${CMAKE_SOURCE_DIR}/deploy/systemd/perceptshift-ros-runtime"
  "${CMAKE_SOURCE_DIR}/deploy/systemd/perceptshift-api-service"
  DESTINATION "lib/perceptshift/bin"
  COMPONENT core
)
install(PROGRAMS
  "${CMAKE_SOURCE_DIR}/deploy/bin/perceptshift-api"
  "${CMAKE_SOURCE_DIR}/deploy/bin/perceptshift"
  DESTINATION "bin"
  COMPONENT core
)

# Python packages: install source trees for site-packages style layout under
# /usr/share/perceptshift/python so the Debian postinst can symlink/entrypoint.
install(DIRECTORY "${CMAKE_SOURCE_DIR}/python/perceptshift_common"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/python"
  COMPONENT core
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.egg-info" EXCLUDE
  PATTERN ".pytest_cache" EXCLUDE
  PATTERN ".ruff_cache" EXCLUDE
)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/python/perceptshift_cli"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/python"
  COMPONENT core
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.egg-info" EXCLUDE
  PATTERN ".pytest_cache" EXCLUDE
  PATTERN ".ruff_cache" EXCLUDE
)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/python/perceptshift_api"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/python"
  COMPONENT core
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.egg-info" EXCLUDE
  PATTERN ".pytest_cache" EXCLUDE
  PATTERN ".ruff_cache" EXCLUDE
  PATTERN "tests" EXCLUDE
)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/python/perceptshift_forge"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/python"
  COMPONENT core
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.egg-info" EXCLUDE
  PATTERN ".pytest_cache" EXCLUDE
  PATTERN ".ruff_cache" EXCLUDE
  PATTERN "tests" EXCLUDE
)

# Web console build artifacts when present at install time.
if(EXISTS "${CMAKE_SOURCE_DIR}/web/apps/console/dist")
  install(DIRECTORY "${CMAKE_SOURCE_DIR}/web/apps/console/dist/"
    DESTINATION "${CMAKE_INSTALL_DATADIR}/perceptshift/console"
    COMPONENT core
  )
endif()

# CPack: monolithic package (component install disabled for v1 coherence).
set(CPACK_PACKAGE_NAME "perceptshift")
set(CPACK_PACKAGE_VENDOR "PerceptShift")
set(CPACK_PACKAGE_CONTACT "maintainers@perceptshift.local")
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY
    "Deadline-aware adaptive ONNX inference for Arm64 ROS 2")
set(CPACK_RESOURCE_FILE_LICENSE "${CMAKE_SOURCE_DIR}/LICENSE")
set(CPACK_RESOURCE_FILE_README "${CMAKE_SOURCE_DIR}/README.md")
set(CPACK_PACKAGE_VERSION "${PERCEPTSHIFT_VERSION}")
set(CPACK_GENERATOR "DEB")
set(CPACK_DEBIAN_FILE_NAME DEB-DEFAULT)
set(CPACK_DEBIAN_PACKAGE_SECTION "science")
set(CPACK_DEBIAN_PACKAGE_SHLIBDEPS OFF)
set(CPACK_DEBIAN_PACKAGE_GENERATE_SHLIBS OFF)
# Runtime deps for the monolithic v1 package. ROS Jazzy is a documented
# prerequisite for the installed runtime service; Python app deps are shipped
# inside /usr/lib/perceptshift/py by scripts/build-release-deb.sh (not apt).
set(CPACK_DEBIAN_PACKAGE_DEPENDS
  "libc6, libstdc++6, libssl3 | libssl1.1, python3 (>= 3.12), adduser, ros-jazzy-rclcpp, ros-jazzy-rclcpp-lifecycle, ros-jazzy-sensor-msgs, ros-jazzy-launch-ros, ros-jazzy-rclpy, ros-jazzy-lifecycle-msgs")
set(CPACK_DEBIAN_PACKAGE_CONTROL_EXTRA
  "${CMAKE_SOURCE_DIR}/packaging/debian/perceptshift.postinst;${CMAKE_SOURCE_DIR}/packaging/debian/perceptshift.prerm;${CMAKE_SOURCE_DIR}/packaging/debian/perceptshift.postrm")
set(CPACK_DEB_COMPONENT_INSTALL OFF)
set(CPACK_COMPONENTS_ALL core)
include(CPack)
