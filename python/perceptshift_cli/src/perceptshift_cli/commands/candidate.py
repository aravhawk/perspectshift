"""candidate command group."""

from __future__ import annotations

from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_common.hashing import write_atomic_json
from perceptshift_common.schema import load_config_document, load_json_document, validate_document
from perceptshift_forge.candidates import generate_candidates

app = typer.Typer(help="Candidate generation and validation")


@app.command("generate")
def generate_cmd(
    ctx: typer.Context,
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
    output_dir: Path = typer.Option(..., "--output-dir"),
    maximum_candidates: int = typer.Option(256, "--maximum-candidates"),
) -> None:
    forge_config = validate_document(load_config_document(config), "forge_config")
    baseline = Path(forge_config["model"]["baseline_path"])
    specs = generate_candidates(
        forge_config,
        baseline_model_path=baseline,
        maximum_candidates=maximum_candidates,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        write_atomic_json(output_dir / f"{spec.candidate_id}.json", spec.manifest)
    output.emit(ctx, {"count": len(specs), "output_dir": str(output_dir)})


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    manifests_dir: Path = typer.Argument(..., exists=True, file_okay=False),
) -> None:
    items = []
    for path in sorted(manifests_dir.glob("*.json")):
        doc = load_json_document(path)
        items.append(
            {
                "candidate_id": doc.get("candidate_id"),
                "label": doc.get("label"),
                "path": str(path),
            }
        )
    output.emit(ctx, {"candidates": items})


@app.command("validate")
def validate_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    doc = validate_document(load_json_document(path), "candidate_manifest")
    output.emit(ctx, {"ok": True, "candidate_id": doc.get("candidate_id")})
