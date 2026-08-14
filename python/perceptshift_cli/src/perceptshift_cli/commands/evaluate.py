"""evaluate command group."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_forge.evaluation import classification_accuracy, coco_map_50_95

app = typer.Typer(help="Quality evaluation")


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    predictions: Path = typer.Option(..., "--predictions", exists=True, dir_okay=False),
    metric: str = typer.Option("classification_accuracy", "--metric"),
    dataset_hash: str = typer.Option(..., "--dataset-hash"),
    adapter_name: str = typer.Option("image_classification", "--adapter-name"),
    coco_gt: Path | None = typer.Option(None, "--coco-gt"),
) -> None:
    payload = json.loads(predictions.read_text(encoding="utf-8"))
    if metric == "classification_accuracy":
        result = classification_accuracy(
            list(payload["predictions"]),
            list(payload["labels"]),
            dataset_hash=dataset_hash,
            adapter_name=adapter_name,
        )
    elif metric == "coco_map_50_95":
        if coco_gt is None:
            raise typer.BadParameter("--coco-gt is required for coco_map_50_95")
        result = coco_map_50_95(
            coco_gt,
            list(payload["detections"]),
            dataset_hash=dataset_hash,
            adapter_name=adapter_name,
        )
    else:
        raise typer.BadParameter(f"Unsupported metric: {metric}")
    output.emit(ctx, result.attestation)


@app.command("compare")
def compare_cmd(
    ctx: typer.Context,
    left: Path = typer.Argument(..., exists=True, dir_okay=False),
    right: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    a = json.loads(left.read_text(encoding="utf-8"))
    b = json.loads(right.read_text(encoding="utf-8"))
    output.emit(
        ctx,
        {
            "left_value": a.get("candidate_value"),
            "right_value": b.get("candidate_value"),
            "delta": (
                None
                if a.get("candidate_value") is None or b.get("candidate_value") is None
                else float(b["candidate_value"]) - float(a["candidate_value"])
            ),
        },
    )
