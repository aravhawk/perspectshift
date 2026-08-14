"""Composable container launch for PerceptShift runtime."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
from ament_index_python.packages import get_package_share_directory
import os


def _launch_setup(context, *args, **kwargs):
    bundle_path = LaunchConfiguration('bundle_path').perform(context)
    if not bundle_path:
        raise RuntimeError(
            'bundle_path is required and must point to a user-supplied profile bundle.'
        )

    params_file = LaunchConfiguration('params_file').perform(context)
    use_intra_process = LaunchConfiguration('use_intra_process').perform(context).lower() in (
        '1', 'true', 'yes'
    )

    container = ComposableNodeContainer(
        name='perceptshift_container',
        namespace='',
        package='rclcpp_components',
        executable='component_container_mt',
        composable_node_descriptions=[
            ComposableNode(
                package='perceptshift_ros',
                plugin='perceptshift_ros::RuntimeNode',
                name='perceptshift_runtime',
                parameters=[
                    params_file,
                    {'bundle_path': bundle_path},
                ],
                extra_arguments=[{'use_intra_process_comms': use_intra_process}],
            ),
        ],
        output='screen',
    )
    return [container]


def generate_launch_description():
    share = get_package_share_directory('perceptshift_bringup')
    default_params = os.path.join(share, 'config', 'runtime_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('bundle_path', default_value=''),
        DeclareLaunchArgument('params_file', default_value=default_params),
        DeclareLaunchArgument(
            'use_intra_process',
            default_value='true',
            description='Enable intra-process communication where supported',
        ),
        OpaqueFunction(function=_launch_setup),
    ])
