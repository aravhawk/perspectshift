"""Filesystem safety helpers shared across Python packages."""

from __future__ import annotations

from pathlib import Path

from perceptshift_common.errors import ErrorCode, PerceptShiftError


def require_absolute(path: Path, *, field: str) -> Path:
    if not path.is_absolute():
        raise PerceptShiftError(
            code=ErrorCode.PATH_UNSAFE,
            message=f"{field} must be an absolute path",
            details={"path": str(path)},
        )
    return path


def resolve_under_root(
    root: Path,
    relative: str | Path,
    *,
    allow_symlinks: bool = False,
    field: str = "path",
) -> Path:
    """Resolve a relative path and reject escapes / disallowed symlinks."""
    root_resolved = require_absolute(root, field="root").resolve(strict=False)
    candidate = (root_resolved / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise PerceptShiftError(
            code=ErrorCode.PATH_UNSAFE,
            message=f"{field} escapes dataset root",
            remediation="Keep all dataset paths under the declared root",
            details={"root": str(root_resolved), "path": str(candidate)},
        ) from exc

    probe = root_resolved / relative
    if probe.is_symlink() and not allow_symlinks:
        raise PerceptShiftError(
            code=ErrorCode.PATH_UNSAFE,
            message=f"{field} resolves through a symlink which is rejected by policy",
            remediation="Replace symlinks with real files or enable an explicit symlink policy",
            details={"path": str(probe)},
        )
    return candidate
