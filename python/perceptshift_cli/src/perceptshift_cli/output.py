"""CLI output helpers."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer
from rich.console import Console

# Human-facing console only. Never used for --json machine output.
console = Console()


def emit_json(payload: dict[str, Any]) -> None:
    """Write exact UTF-8 JSON + newline with no ANSI, highlighting, or prose."""
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    # Plain stdout write — immune to FORCE_COLOR / Rich highlighting / TTY.
    sys.stdout.write(text)
    sys.stdout.flush()


def emit(ctx: typer.Context, payload: dict[str, Any], *, human: str | None = None) -> None:
    obj = ctx.ensure_object(dict)
    if obj.get("quiet") and not obj.get("json"):
        return
    if obj.get("json"):
        emit_json(payload)
        return
    console.print(human if human is not None else json.dumps(payload, indent=2, sort_keys=True))
