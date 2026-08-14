"""Product version helpers."""

from __future__ import annotations

from functools import lru_cache
from importlib import metadata
from pathlib import Path

__version__ = "0.1.0"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the installed package version, falling back to VERSION or __version__."""
    try:
        return metadata.version("perceptshift-common")
    except metadata.PackageNotFoundError:
        pass
    root = Path(__file__).resolve().parents[4]
    version_file = root / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return __version__
