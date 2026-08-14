"""dataset command group."""

from __future__ import annotations

from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_common.hashing import sha256_canonical
from perceptshift_forge.datasets import summarize_result
from perceptshift_forge.datasets.validate import validate_dataset_manifest

app = typer.Typer(help="Dataset validation and hashing")


@app.command("validate")
def validate_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    allow_symlinks: bool = typer.Option(False, "--allow-symlinks"),
) -> None:
    result = validate_dataset_manifest(path, allow_symlinks=allow_symlinks)
    payload = summarize_result(result)
    output.emit(ctx, payload)
    if not result.ok:
        raise typer.Exit(code=2)


@app.command("hash")
def hash_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    result = validate_dataset_manifest(path)
    payload = {
        "manifest_hash": result.manifest_hash,
        "content_hash_digest": sha256_canonical(result.content_hashes),
        "item_count": result.item_count,
    }
    output.emit(ctx, payload)


@app.command("summarize")
def summarize_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    result = validate_dataset_manifest(path)
    output.emit(ctx, summarize_result(result))
