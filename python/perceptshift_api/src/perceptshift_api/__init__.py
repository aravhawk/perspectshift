"""PerceptShift local operational API."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    from perceptshift_common.version import get_version as _common_version

    __version__ = _common_version()
except (ImportError, ModuleNotFoundError):
    try:
        __version__ = version("perceptshift-api")
    except PackageNotFoundError:  # pragma: no cover
        __version__ = "0.1.0"


def health() -> dict[str, str]:
    return {"status": "ok", "product": "perceptshift", "version": __version__}


__all__ = ["__version__", "health"]
