"""Producer metadata for durable documents."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from perceptshift_common.version import get_version


@lru_cache(maxsize=1)
def git_commit() -> str:
    env_commit = os.environ.get("PERCEPTSHIFT_GIT_COMMIT")
    if env_commit:
        return env_commit.strip()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    commit = result.stdout.strip()
    return commit or "unknown"


def utc_now_rfc3339() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def producer_metadata() -> dict[str, str]:
    return {
        "product": "perceptshift",
        "version": get_version(),
        "git_commit": git_commit(),
    }


def envelope_fields(*, document_type: str, schema_version: str = "1.0") -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "document_type": document_type,
        "created_at": utc_now_rfc3339(),
        "producer": producer_metadata(),
    }
