"""report command group."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_forge.reporting import (
    build_report_document,
    export_html,
    export_json,
    export_markdown,
    sanitize_report,
)

app = typer.Typer(help="Report build/export/sanitize")


@app.command("build")
def build_cmd(
    ctx: typer.Context,
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False),
    output_dir: Path = typer.Option(..., "--output-dir"),
) -> None:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    report = build_report_document(raw)
    output_dir.mkdir(parents=True, exist_ok=True)
    export_json(report, output_dir / "report.json")
    export_markdown(report, output_dir / "report.md")
    export_html(report, output_dir / "report.html")
    output.emit(ctx, {"ok": True, "output_dir": str(output_dir)})


@app.command("serve")
def serve_cmd(ctx: typer.Context, path: Path = typer.Argument(..., exists=True)) -> None:
    """Print the report path for a local static viewer; does not start a network server."""
    output.emit(ctx, {"path": str(path.resolve()), "mode": "static-file"})


@app.command("export")
def export_cmd(
    ctx: typer.Context,
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False),
    output_path: Path = typer.Option(..., "--output"),
    format_name: str = typer.Option("json", "--format"),
) -> None:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    report = build_report_document(raw)
    if format_name == "json":
        export_json(report, output_path)
    elif format_name == "markdown":
        export_markdown(report, output_path)
    elif format_name == "html":
        export_html(report, output_path)
    else:
        raise typer.BadParameter("format must be json|markdown|html")
    output.emit(ctx, {"ok": True, "output": str(output_path)})


@app.command("sanitize")
def sanitize_cmd(
    ctx: typer.Context,
    input_path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_path: Path = typer.Option(..., "--output"),
) -> None:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    cleaned = sanitize_report(raw)
    output_path.write_text(json.dumps(cleaned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.emit(ctx, {"ok": True, "output": str(output_path)})
