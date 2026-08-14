"""Bringup launch file presence and argument contract tests."""

from pathlib import Path


def test_launch_files_exist():
    launch_dir = Path(__file__).resolve().parents[1] / 'launch'
    expected = {
        'runtime.launch.py',
        'composable.launch.py',
        'with_lifecycle_manager.launch.py',
        'with_api.launch.py',
        'tracing.launch.py',
    }
    present = {p.name for p in launch_dir.glob('*.launch.py')}
    assert expected.issubset(present)


def test_config_requires_empty_default_bundle_path():
    params = (Path(__file__).resolve().parents[1] / 'config' / 'runtime_params.yaml').read_text()
    assert 'bundle_path: ""' in params
    assert 'yolo_v8_detection' in params
