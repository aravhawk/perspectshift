"""Typer CLI application for PerceptShift."""

from __future__ import annotations

import json
from typing import Any

import typer

from perceptshift_cli import output
from perceptshift_cli.commands import (
    benchmark,
    bundle,
    candidate,
    certify,
    dataset,
    evaluate,
    forge,
    inspect,
    model,
    report,
    run_cmd,
    runtime,
    system,
)
from perceptshift_common.errors import PerceptShiftError
from perceptshift_common.version import get_version
from perceptshift_forge.inspection import run_doctor

app = typer.Typer(
    name="perceptshift",
    help="PerceptShift operator CLI",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(inspect.app, name="inspect")
app.add_typer(dataset.app, name="dataset")
app.add_typer(model.app, name="model")
app.add_typer(candidate.app, name="candidate")
app.add_typer(benchmark.app, name="benchmark")
app.add_typer(evaluate.app, name="evaluate")
app.add_typer(forge.app, name="forge")
app.add_typer(certify.app, name="certify")
app.add_typer(bundle.app, name="bundle")
app.add_typer(report.app, name="report")
app.add_typer(run_cmd.app, name="run")
app.add_typer(system.app, name="system")
app.add_typer(runtime.app, name="runtime")


def _version_option(value: bool) -> None:
    if not value:
        return
    typer.echo(f"perceptshift {get_version()}")
    raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress non-error output"),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose diagnostics"),
    version: bool = typer.Option(
        False,
        "--version",
        help="Print product version and exit",
        callback=_version_option,
        is_eager=True,
    ),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["quiet"] = quiet
    ctx.obj["verbose"] = verbose
    _ = version


@app.command("version")
def version_cmd(
    ctx: typer.Context,
) -> None:
    """Print product version."""
    payload = {"product": "perceptshift", "version": get_version()}
    output.emit(ctx, payload, human=f"perceptshift {get_version()}")


@app.command("doctor")
def doctor_cmd(ctx: typer.Context) -> None:
    """Run host/dependency doctor checks."""
    report_doc = run_doctor()
    output.emit(ctx, report_doc, human=json.dumps(report_doc, indent=2))


def main() -> None:
    try:
        app()
    except PerceptShiftError as exc:
        payload: dict[str, Any] = exc.to_dict()
        # Errors always emit raw JSON on stdout (machine-contract), never Rich/ANSI.
        output.emit_json(payload)
        raise typer.Exit(code=2) from exc


if __name__ == "__main__":
    main()
