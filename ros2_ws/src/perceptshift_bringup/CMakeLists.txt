cmake_minimum_required(VERSION 3.22)
project(perceptshift_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_launch_files test/test_launch_files.py)
endif()

ament_package()
