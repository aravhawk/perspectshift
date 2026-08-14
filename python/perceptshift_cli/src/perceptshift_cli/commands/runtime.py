"""runtime status (best-effort)."""

from __future__ import annotations

import json

import httpx
import typer

from perceptshift_cli import output
from perceptshift_common.paths import runtime_dir
from perceptshift_common.reason_codes import ReasonCode

app = typer.Typer(help="Runtime status helpers")


@app.command("status")
def status_cmd(
    ctx: typer.Context,
    api_url: str = typer.Option("http://127.0.0.1:8787", "--api-url"),
) -> None:
    """Best-effort runtime status via local API or runtime state file."""
    state_file = None
    rt = runtime_dir()
    if rt is not None:
        candidate = rt / "runtime-state.json"
        if candidate.is_file():
            state_file = candidate
    if state_file is not None:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        output.emit(ctx, {"source": "runtime_state_file", "status": payload})
        return
    try:
        response = httpx.get(f"{api_url.rstrip('/')}/v1/runtime/status", timeout=1.0)
        if response.status_code == 200:
            output.emit(ctx, {"source": "api", "status": response.json()})
            return
        output.emit(
            ctx,
            {
                "source": "api",
                "available": False,
                "reason_code": ReasonCode.UNAVAILABLE_RUNTIME_STATUS,
                "http_status": response.status_code,
            },
        )
    except httpx.HTTPError as exc:
        output.emit(
            ctx,
            {
                "source": "api",
                "available": False,
                "reason_code": ReasonCode.UNAVAILABLE_RUNTIME_STATUS,
                "message": str(exc),
            },
        )
