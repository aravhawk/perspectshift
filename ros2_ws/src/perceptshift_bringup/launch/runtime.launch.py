"""Standalone lifecycle node launch. Requires bundle_path."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LifecycleNode
from ament_index_python.packages import get_package_share_directory
import os


def _launch_setup(context, *args, **kwargs):
    bundle_path = LaunchConfiguration('bundle_path').perform(context)
    if not bundle_path:
        raise RuntimeError(
            'bundle_path is required and must point to a user-supplied profile bundle. '
            'PerceptShift does not ship models or datasets.'
        )

    params_file = LaunchConfiguration('params_file').perform(context)
    image_topic = LaunchConfiguration('image_topic').perform(context)
    enable_tracing = LaunchConfiguration('enable_tracing').perform(context)
    task = LaunchConfiguration('task').perform(context)
    deadline_ms = LaunchConfiguration('deadline_ms').perform(context)
    enable_mutation_services = LaunchConfiguration('enable_mutation_services').perform(context)
    require_signature = LaunchConfiguration('require_signature').perform(context)
    maximum_source_age_ms = LaunchConfiguration('maximum_source_age_ms').perform(context)
    telemetry_period_ms = LaunchConfiguration('telemetry_period_ms').perform(context)
    # Optional unused alias kept for systemd wrapper compatibility.
    _ = LaunchConfiguration('runtime_config').perform(context)

    overrides = {
        'bundle_path': bundle_path,
        'image_topic': image_topic,
        'enable_tracing': enable_tracing.lower() in ('1', 'true', 'yes'),
        'enable_mutation_services': enable_mutation_services.lower() in ('1', 'true', 'yes'),
        'require_signature': require_signature.lower() in ('1', 'true', 'yes'),
    }
    if task:
        overrides['task'] = task
    if deadline_ms:
        overrides['deadline_ms'] = float(deadline_ms)
    if maximum_source_age_ms:
        overrides['maximum_source_age_ms'] = float(maximum_source_age_ms)
    if telemetry_period_ms:
        # Node declares telemetry_period_ms as integer.
        overrides['telemetry_period_ms'] = int(float(telemetry_period_ms))

    node = LifecycleNode(
        package='perceptshift_ros',
        executable='perceptshift_runtime_node',
        name='perceptshift_runtime',
        namespace='',
        output='screen',
        parameters=[
            params_file,
            overrides,
        ],
    )
    return [node]


def generate_launch_description():
    share = get_package_share_directory('perceptshift_bringup')
    default_params = os.path.join(share, 'config', 'runtime_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'bundle_path',
            default_value='',
            description='Absolute path to a user-supplied certified profile bundle',
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Runtime ROS parameters YAML',
        ),
        DeclareLaunchArgument(
            'image_topic',
            default_value='/camera/image_raw',
            description='Input image topic',
        ),
        DeclareLaunchArgument(
            'enable_tracing',
            default_value='false',
            description='Enable optional low-overhead trace hooks',
        ),
        DeclareLaunchArgument(
            'task',
            default_value='',
            description='Optional task override (e.g. image_classification)',
        ),
        DeclareLaunchArgument(
            'deadline_ms',
            default_value='',
            description='Optional deadline override in milliseconds',
        ),
        DeclareLaunchArgument(
            'enable_mutation_services',
            default_value='true',
            description='Enable operator mutation services',
        ),
        DeclareLaunchArgument(
            'require_signature',
            default_value='false',
            description='Require Ed25519 bundle signatures',
        ),
        DeclareLaunchArgument(
            'maximum_source_age_ms',
            default_value='',
            description='Optional source-age override',
        ),
        DeclareLaunchArgument(
            'telemetry_period_ms',
            default_value='',
            description='Optional telemetry period override',
        ),
        DeclareLaunchArgument(
            'runtime_config',
            default_value='',
            description='Optional unused config path (systemd wrapper compatibility)',
        ),
        OpaqueFunction(function=_launch_setup),
    ])
