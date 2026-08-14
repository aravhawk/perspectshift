"""Runtime plus local API process. Bundle path is still user-supplied."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _launch_setup(context, *args, **kwargs):
    bundle_path = LaunchConfiguration('bundle_path').perform(context)
    if not bundle_path:
        raise RuntimeError('bundle_path is required')

    api_bind = LaunchConfiguration('api_bind').perform(context)
    host, _, port = api_bind.partition(':')
    if not host:
        host = '127.0.0.1'
    if not port:
        port = '8080'
    share = get_package_share_directory('perceptshift_bringup')

    runtime = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'runtime.launch.py')),
        launch_arguments={'bundle_path': bundle_path}.items(),
    )

    api = ExecuteProcess(
        cmd=[
            'perceptshift-api',
            '--host', host,
            '--port', port,
        ],
        output='screen',
        additional_env={
            'PERCEPTSHIFT_API_ENABLE_ROS': 'true',
        },
    )
    return [runtime, api]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('bundle_path', default_value=''),
        DeclareLaunchArgument(
            'api_bind',
            default_value='127.0.0.1:8080',
            description='Local API bind address (loopback by default)',
        ),
        OpaqueFunction(function=_launch_setup),
    ])
