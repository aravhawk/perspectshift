"""bundle command group."""

from __future__ import annotations

from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_common.hashing import sha256_file, write_atomic_json, write_atomic_text
from perceptshift_common.producer import envelope_fields, producer_metadata, utc_now_rfc3339
from perceptshift_common.version import get_version
from perceptshift_forge.bundle import import_bundle, sign_bundle, verify_bundle

app = typer.Typer(help="Profile bundle operations")


@app.command("create")
def create_cmd(
    ctx: typer.Context,
    output_dir: Path = typer.Option(..., "--output"),
    profile_id: str = typer.Option("profile-0", "--profile-id"),
    model: Path | None = typer.Option(
        None, "--model", exists=True, dir_okay=False, help="Certified model artifact to include"
    ),
) -> None:
    """Create a bundle only from a real model artifact.

    Refuses placeholder models and zero hashes. Prefer Forge certification output.
    """
    if model is None:
        raise typer.BadParameter(
            "bundle create requires --model PATH to a real ONNX artifact; "
            "placeholder/zero-hash draft bundles are not supported"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "models").mkdir(exist_ok=True)
    (output_dir / "profiles").mkdir(exist_ok=True)
    (output_dir / "attestations").mkdir(exist_ok=True)
    (output_dir / "schemas").mkdir(exist_ok=True)
    rel_model = f"models/{profile_id}.onnx"
    dest = output_dir / rel_model
    dest.write_bytes(model.read_bytes())
    model_hash = sha256_file(dest)
    if set(model_hash) == {"0"}:
        raise typer.BadParameter("refusing zero model hash")
    write_atomic_text(output_dir / "NOTICE", "PerceptShift profile bundle\n")
    notice_hash = sha256_file(output_dir / "NOTICE")
    profile = {
        "profile_id": profile_id,
        "label": profile_id,
        "model_sha256": model_hash,
        "model_relative_path": rel_model,
        "status": "operator_provided",
        "session": {
            "provider_order": ["CPUExecutionProvider"],
            "intra_op_threads": 1,
            "inter_op_threads": 1,
            "graph_optimization_level": "all",
        },
        "adapter": {"name": "raw_tensor"},
        "preprocess": {"backend": "scalar"},
    }
    write_atomic_json(output_dir / "profiles" / f"{profile_id}.json", profile)
    profile_hash = sha256_file(output_dir / "profiles" / f"{profile_id}.json")
    manifest = envelope_fields(document_type="perceptshift.profile_bundle")
    manifest.update(
        {
            "bundle_id": f"bundle-{profile_id}",
            "product_version": get_version(),
            "minimum_compatible_runtime_version": "0.1.0",
            "producer": producer_metadata(),
            "created_at": utc_now_rfc3339(),
            "adapter": {"name": "raw_tensor"},
            "quality_metric_name": "numeric_equivalence",
            "quality_direction": "higher_is_better",
            "profiles": [profile],
            "files": [
                {
                    "path": "NOTICE",
                    "sha256": notice_hash,
                    "size_bytes": (output_dir / "NOTICE").stat().st_size,
                },
                {
                    "path": f"profiles/{profile_id}.json",
                    "sha256": profile_hash,
                    "size_bytes": (output_dir / "profiles" / f"{profile_id}.json").stat().st_size,
                },
                {
                    "path": rel_model,
                    "sha256": model_hash,
                    "size_bytes": dest.stat().st_size,
                },
            ],
        }
    )
    write_atomic_json(output_dir / "manifest.json", manifest)
    digest = sha256_file(output_dir / "manifest.json")
    write_atomic_text(output_dir / "manifest.sha256", digest + "\n")
    output.emit(ctx, verify_bundle(output_dir))


@app.command("verify")
def verify_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, file_okay=False),
) -> None:
    output.emit(ctx, verify_bundle(path))


@app.command("import")
def import_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, file_okay=False),
    destination: Path = typer.Option(..., "--destination"),
) -> None:
    output.emit(ctx, import_bundle(path, destination))


@app.command("sign")
def sign_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, file_okay=False),
    key: Path = typer.Option(..., "--key", exists=True, dir_okay=False),
) -> None:
    output.emit(ctx, sign_bundle(path, key_path=key))


@app.command("inspect")
def inspect_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, file_okay=False),
) -> None:
    output.emit(ctx, verify_bundle(path))
