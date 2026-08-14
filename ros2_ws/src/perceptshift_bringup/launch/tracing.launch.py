"""Tracing-enabled runtime launch."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _launch_setup(context, *args, **kwargs):
    bundle_path = LaunchConfiguration('bundle_path').perform(context)
    if not bundle_path:
        raise RuntimeError('bundle_path is required')

    share = get_package_share_directory('perceptshift_bringup')
    runtime = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'runtime.launch.py')),
        launch_arguments={
            'bundle_path': bundle_path,
            'enable_tracing': 'true',
        }.items(),
    )
    return [
        SetEnvironmentVariable('PERCEPTSHIFT_TRACING', '1'),
        runtime,
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('bundle_path', default_value=''),
        OpaqueFunction(function=_launch_setup),
    ])
