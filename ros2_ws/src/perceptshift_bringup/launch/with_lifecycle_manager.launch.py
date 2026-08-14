"""Lifecycle node plus lifecycle manager."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_setup(context, *args, **kwargs):
    bundle_path = LaunchConfiguration('bundle_path').perform(context)
    if not bundle_path:
        raise RuntimeError('bundle_path is required')

    share = get_package_share_directory('perceptshift_bringup')
    runtime = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'runtime.launch.py')),
        launch_arguments={
            'bundle_path': bundle_path,
            'params_file': LaunchConfiguration('params_file').perform(context),
            'image_topic': LaunchConfiguration('image_topic').perform(context),
        }.items(),
    )

    manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_perceptshift',
        output='screen',
        parameters=[os.path.join(share, 'config', 'lifecycle_manager.yaml')],
    )
    return [runtime, manager]


def generate_launch_description():
    share = get_package_share_directory('perceptshift_bringup')
    return LaunchDescription([
        DeclareLaunchArgument('bundle_path', default_value=''),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(share, 'config', 'runtime_params.yaml'),
        ),
        DeclareLaunchArgument('image_topic', default_value='/camera/image_raw'),
        OpaqueFunction(function=_launch_setup),
    ])
