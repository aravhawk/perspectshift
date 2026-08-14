cmake_minimum_required(VERSION 3.22)
project(perceptshift_msgs)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

set(msg_files
  "msg/Classification.msg"
  "msg/ClassificationArray.msg"
  "msg/Detection.msg"
  "msg/DetectionArray.msg"
  "msg/RuntimeHealth.msg"
  "msg/ProfileState.msg"
  "msg/InferenceTrace.msg"
  "msg/SwitchEvent.msg"
  "msg/ControlHoldRequest.msg"
)

set(srv_files
  "srv/GetRuntimeStatus.srv"
  "srv/PinProfile.srv"
  "srv/ClearProfilePin.srv"
  "srv/UpdateRuntimePolicy.srv"
  "srv/RequestRecovery.srv"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  DEPENDENCIES builtin_interfaces std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
