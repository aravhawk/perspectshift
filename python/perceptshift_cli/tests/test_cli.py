"""CLI smoke tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

from perceptshift_cli.app import app
from perceptshift_common.version import get_version

runner = CliRunner()


def _assert_raw_json(stdout: str) -> dict:
    assert "\x1b[" not in stdout, f"ANSI escape in --json output: {stdout!r}"
    return json.loads(stdout)


def test_version() -> None:
    result = runner.invoke(app, ["--json", "version"])
    assert result.exit_code == 0, result.stdout + str(result.exception)
    payload = _assert_raw_json(result.stdout)
    assert get_version() in payload["version"]


def test_system_paths() -> None:
    result = runner.invoke(app, ["--json", "system", "paths"])
    assert result.exit_code == 0, result.stdout + str(result.exception)
    payload = _assert_raw_json(result.stdout)
    assert "config" in payload or "paths" in str(payload).lower() or "config" in result.stdout


def test_doctor() -> None:
    result = runner.invoke(app, ["--json", "doctor"])
    assert result.exit_code == 0, result.stdout + str(result.exception)
    payload = _assert_raw_json(result.stdout)
    assert "dependencies" in payload or "dependencies" in result.stdout


def _write_dataset_manifest(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8)).save(root / "a.png")
    man = {
        "schema_version": "1.0",
        "document_type": "perceptshift.dataset_manifest",
        "dataset_type": "image_classification_manifest",
        "dataset_name": "cli",
        "root": str(root),
        "license_reference": "test",
        "split_name": "cal",
        "preprocess_contract": {
            "input_width": 4,
            "input_height": 4,
            "input_layout": "nchw",
            "accepted_source_formats": ["rgb8", "bgr8", "rgba8", "bgra8", "mono8"],
            "source_color_handling": "convert_to_rgb",
            "resize_mode": "stretch",
            "resize_interpolation": "bilinear",
            "scale": 1.0 / 255.0,
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
            "swap_rb": False,
            "letterbox_pad_value": None,
            "output_dtype": "float32",
            "backend": "scalar",
        },
        "items": [{"path": "a.png", "class_id": 0}],
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(man), encoding="utf-8")
    return path


def test_dataset_validate(tmp_path: Path) -> None:
    path = _write_dataset_manifest(tmp_path)
    result = runner.invoke(app, ["--json", "dataset", "validate", str(path)])
    assert result.exit_code == 0, result.stdout + str(result.exception)
    payload = _assert_raw_json(result.stdout)
    assert payload["ok"] is True


@pytest.mark.parametrize(
    "args",
    [
        ["--json", "version"],
        ["--json", "system", "paths"],
        ["--json", "forge", "status"],
    ],
)
def test_json_output_force_color_no_ansi(args: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """--json must remain parseable under FORCE_COLOR=1 / colored TERM."""
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("TERM", "xterm-color")
    # Rich/colorama may also consult these.
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    result = runner.invoke(app, args, env={**os.environ, "FORCE_COLOR": "1", "TERM": "xterm-color"})
    assert result.exit_code == 0, result.stdout + str(result.exception)
    _assert_raw_json(result.stdout)


def test_dataset_validate_force_color_raw_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("TERM", "xterm-color")
    path = _write_dataset_manifest(tmp_path)
    result = runner.invoke(
        app,
        ["--json", "dataset", "validate", str(path)],
        env={**os.environ, "FORCE_COLOR": "1", "TERM": "xterm-color"},
    )
    assert result.exit_code == 0, result.stdout + str(result.exception)
    payload = _assert_raw_json(result.stdout)
    assert payload["ok"] is True


def test_json_subprocess_force_color_no_ansi(tmp_path: Path) -> None:
    """Subprocess path (real stdout) must stay ANSI-free under FORCE_COLOR."""
    import subprocess
    import sys

    path = _write_dataset_manifest(tmp_path)
    env = {
        **os.environ,
        "FORCE_COLOR": "1",
        "TERM": "xterm-color",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")
        + os.pathsep
        + str(Path(__file__).resolve().parents[3] / "perceptshift_common" / "src")
        + os.pathsep
        + str(Path(__file__).resolve().parents[3] / "perceptshift_forge" / "src")
        + os.pathsep
        + env_get_existing_pythonpath(),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "perceptshift_cli", "--json", "dataset", "validate", str(path)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = _assert_raw_json(proc.stdout)
    assert payload["ok"] is True


def env_get_existing_pythonpath() -> str:
    return os.environ.get("PYTHONPATH", "")
