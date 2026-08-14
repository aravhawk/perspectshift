"""XDG and system path helpers for PerceptShift."""

from __future__ import annotations

import os
from pathlib import Path


def _home() -> Path:
    return Path.home()


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else _home() / ".config"
    return root / "perceptshift"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else _home() / ".local" / "share"
    return root / "perceptshift"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else _home() / ".local" / "state"
    return root / "perceptshift"


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else _home() / ".cache"
    return root / "perceptshift"


def runtime_dir() -> Path | None:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        return None
    return Path(base) / "perceptshift"


def runs_index_dir() -> Path:
    return data_dir() / "runs"


def ensure_dir(path: Path, *, mode: int = 0o750) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=mode)
    try:
        path.chmod(mode)
    except OSError:
        pass
    return path


def path_inventory() -> dict[str, str | None]:
    runtime = runtime_dir()
    return {
        "config": str(config_dir()),
        "data": str(data_dir()),
        "state": str(state_dir()),
        "cache": str(cache_dir()),
        "runtime": str(runtime) if runtime is not None else None,
        "runs_index": str(runs_index_dir()),
    }
