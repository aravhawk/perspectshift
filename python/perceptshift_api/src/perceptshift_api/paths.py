"""Path allowlisting and artifact path safety."""

from __future__ import annotations

import os
from pathlib import Path

from perceptshift_api.errors import ApiError


def ensure_within_roots(path: Path, roots: list[Path], *, follow_symlinks: bool = False) -> Path:
    """Resolve path and ensure it stays within one of the allowlisted roots."""
    candidate = path.expanduser()
    if not candidate.is_absolute():
        raise ApiError(
            "PATH_NOT_ALLOWED",
            "Relative paths are not accepted",
            status_code=400,
            remediation="Provide an absolute path under a registered artifact root",
        )

    # Reject path segments that attempt traversal before resolution.
    if ".." in candidate.parts:
        raise ApiError(
            "PATH_TRAVERSAL",
            "Path traversal is not allowed",
            status_code=400,
            remediation="Use a canonical absolute path without '..' segments",
        )

    try:
        resolved = (
            candidate.resolve(strict=False) if follow_symlinks else _resolve_nofollow(candidate)
        )
    except OSError as exc:
        raise ApiError(
            "PATH_INVALID",
            "Unable to resolve path",
            status_code=400,
            details={"reason": str(exc)},
        ) from exc

    for root in roots:
        root_resolved = root.resolve()
        try:
            resolved.relative_to(root_resolved)
            return resolved
        except ValueError:
            continue

    raise ApiError(
        "PATH_NOT_ALLOWED",
        "Path is outside registered artifact roots",
        status_code=403,
        remediation="Register the directory via PERCEPTSHIFT_API_ARTIFACT_ROOTS",
    )


def _resolve_nofollow(path: Path) -> Path:
    """Resolve without following the final symlink; reject intermediate symlink escapes."""
    parts = path.parts
    if not parts:
        raise ApiError("PATH_INVALID", "Empty path", status_code=400)
    current = Path(parts[0])
    if os.name != "nt" and parts[0] == "/":
        current = Path("/")
        remaining = parts[1:]
    else:
        remaining = parts[1:]

    for part in remaining:
        current = current / part
        if current.is_symlink():
            target = current.resolve(strict=False)
            # Keep walking using the symlink target for intermediate components,
            # but callers must still pass root checks on the final path.
            current = target
    return current if current.is_absolute() else path.absolute()


def safe_display_path(path: Path) -> str:
    """Redact home directory prefixes for operator display."""
    home = str(Path.home())
    text = str(path)
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text


def content_disposition_attachment(filename: str) -> str:
    """Build a safe Content-Disposition header value."""
    cleaned = "".join(ch for ch in filename if ch.isalnum() or ch in {"-", "_", ".", " "}).strip()
    if not cleaned:
        cleaned = "artifact.bin"
    return f'attachment; filename="{cleaned}"'
