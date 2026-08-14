"""Shared PerceptShift library: schemas, errors, paths, hashing, producer metadata."""

from __future__ import annotations

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.version import __version__, get_version

__all__ = [
    "ErrorCode",
    "PerceptShiftError",
    "__version__",
    "get_version",
]
