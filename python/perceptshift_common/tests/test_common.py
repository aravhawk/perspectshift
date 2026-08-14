"""Common package tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_bytes, sha256_canonical, sha256_file
from perceptshift_common.paths import cache_dir, config_dir, data_dir, path_inventory
from perceptshift_common.producer import producer_metadata
from perceptshift_common.schema import load_schema, validate_document
from perceptshift_common.version import get_version


def test_version_nonzero() -> None:
    assert get_version()


def test_hashing(tmp_path: Path) -> None:
    path = tmp_path / "a.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == sha256_bytes(b"abc")
    assert sha256_canonical({"b": 1, "a": 2}) == sha256_canonical({"a": 2, "b": 1})


def test_paths_respect_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert config_dir() == tmp_path / "cfg" / "perceptshift"
    assert data_dir() == tmp_path / "data" / "perceptshift"
    assert cache_dir() == tmp_path / "cache" / "perceptshift"
    inv = path_inventory()
    assert "config" in inv


def test_producer_metadata() -> None:
    meta = producer_metadata()
    assert meta["product"] == "perceptshift"
    assert meta["version"]
    assert meta["git_commit"]


def test_schema_load_and_reject() -> None:
    schema = load_schema("dataset_manifest")
    assert schema["$id"]
    with pytest.raises(PerceptShiftError) as exc:
        validate_document({"schema_version": "1.0"}, "dataset_manifest")
    assert exc.value.code == ErrorCode.CONFIG_INVALID
