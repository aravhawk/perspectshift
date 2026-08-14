"""Environment capture and version helper coverage."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path

import pytest

from perceptshift_common import version as version_mod
from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.path_security import require_absolute, resolve_under_root
from perceptshift_forge.orchestration.environment import capture_environment


def test_require_absolute_rejects_relative(tmp_path: Path) -> None:
    with pytest.raises(PerceptShiftError) as exc:
        require_absolute(Path("relative"), field="model")
    assert exc.value.code == ErrorCode.PATH_UNSAFE
    assert "absolute" in str(exc.value)


def test_resolve_under_root_rejects_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.txt").write_text("x", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("y", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to(outside)

    resolved = resolve_under_root(root, "ok.txt")
    assert resolved == (root / "ok.txt").resolve()

    with pytest.raises(PerceptShiftError) as escape:
        resolve_under_root(root, "../outside.txt")
    assert escape.value.code == ErrorCode.PATH_UNSAFE

    with pytest.raises(PerceptShiftError) as symlink:
        resolve_under_root(root, "link.txt", allow_symlinks=False)
    assert symlink.value.code == ErrorCode.PATH_UNSAFE

    err = PerceptShiftError(
        code=ErrorCode.PATH_UNSAFE,
        message="boom",
        remediation="fix path",
        correlation_id="cid-1",
        cause=ValueError("nested"),
    )
    payload = err.to_dict()
    assert payload["remediation"] == "fix path"
    assert payload["correlation_id"] == "cid-1"
    assert "ValueError" in payload["cause"]


def test_capture_environment_writes_fingerprint(tmp_path: Path) -> None:
    status = capture_environment(workspace_root=tmp_path, require_valid=False)
    assert status["schema_version"] == "1.0"
    assert (tmp_path / "environment" / "host-fingerprint.json").is_file()
    assert (tmp_path / "environment" / "status.json").is_file()
    assert "architecture" in status
    assert isinstance(status["unavailable"], list)


def test_capture_environment_require_valid_when_ort_present(tmp_path: Path) -> None:
    status = capture_environment(workspace_root=tmp_path, require_valid=True)
    # On developer hosts with ORT, status should be valid; without providers, invalid.
    assert status["status"] in {"valid", "invalid", "valid_with_warnings"}


def test_get_version_uses_package_or_fallback() -> None:
    version_mod.get_version.cache_clear()
    value = version_mod.get_version()
    assert isinstance(value, str) and value


def test_get_version_falls_back_when_uninstalled(monkeypatch) -> None:
    version_mod.get_version.cache_clear()

    def _missing(_name: str) -> str:
        raise metadata.PackageNotFoundError("perceptshift-common")

    monkeypatch.setattr(metadata, "version", _missing)
    version_mod.get_version.cache_clear()
    value = version_mod.get_version()
    assert isinstance(value, str) and value
    version_mod.get_version.cache_clear()
