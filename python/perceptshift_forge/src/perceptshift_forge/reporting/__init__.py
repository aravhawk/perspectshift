"""Factual JSON/Markdown/HTML report generation with path redaction."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any

from perceptshift_common.hashing import write_atomic_text
from perceptshift_common.producer import envelope_fields


def redact_path(text: str, *, home: str | None = None) -> str:
    home_path = home if home is not None else str(Path.home())
    redacted = text.replace(home_path, "${HOME}")
    user = os.environ.get("USER") or os.environ.get("USERNAME")
    if user:
        redacted = re.sub(rf"(?<=/)({re.escape(user)})(?=/)", "${USER}", redacted)
    return redacted


def redact_structure(value: Any, *, home: str | None = None) -> Any:
    if isinstance(value, str):
        return redact_path(value, home=home)
    if isinstance(value, list):
        return [redact_structure(item, home=home) for item in value]
    if isinstance(value, dict):
        return {str(k): redact_structure(v, home=home) for k, v in value.items()}
    return value


def build_report_document(run_data: dict[str, Any]) -> dict[str, Any]:
    doc = envelope_fields(document_type="perceptshift.forge_report")
    doc.update(
        {
            "run_identity": run_data.get("run_identity", {}),
            "host_fingerprint": run_data.get("host_fingerprint"),
            "provenance": run_data.get("provenance", {}),
            "methodology": run_data.get("methodology", {}),
            "preflight": run_data.get("preflight"),
            "candidates": run_data.get("candidates", []),
            "provider_assignment": run_data.get("provider_assignment"),
            "quality": run_data.get("quality", []),
            "latency": run_data.get("latency", []),
            "invalid_trials": run_data.get("invalid_trials", []),
            "pareto": run_data.get("pareto", []),
            "certification_gates": run_data.get("certification_gates", []),
            "selected_profiles": run_data.get("selected_profiles", []),
            "limitations": run_data.get("limitations", []),
            "reproduction": run_data.get("reproduction", {}),
            "artifact_links": run_data.get("artifact_links", []),
        }
    )
    return redact_structure(doc)


def export_json(report: dict[str, Any], path: Path) -> None:
    write_atomic_text(path, json.dumps(report, indent=2, sort_keys=True) + "\n")


def export_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# PerceptShift Forge Report",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- created_at: `{report.get('created_at')}`",
        f"- run_id: `{((report.get('run_identity') or {}).get('run_id'))}`",
        "",
        "## Limitations / unavailable metrics",
        "",
    ]
    limitations = report.get("limitations") or []
    if not limitations:
        lines.append("_None recorded._")
    else:
        for item in limitations:
            lines.append(f"- {json.dumps(item, sort_keys=True)}")
    lines.extend(["", "## Certification gates", ""])
    for gate in report.get("certification_gates") or []:
        lines.append(
            f"- `{gate.get('name')}`: pass={gate.get('pass')} "
            f"required={gate.get('required')} reasons={gate.get('reason_codes')}"
        )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```",
            json.dumps(report.get("reproduction") or {}, indent=2),
            "```",
            "",
        ]
    )
    write_atomic_text(path, "\n".join(lines))


def export_html(report: dict[str, Any], path: Path) -> None:
    body = html.escape(json.dumps(report, indent=2, sort_keys=True))
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>PerceptShift Forge Report</title>
  <style>
    body {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 2rem; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <h1>PerceptShift Forge Report</h1>
  <p>Factual export. No marketing claims. Paths redacted.</p>
  <pre>{body}</pre>
</body>
</html>
"""
    write_atomic_text(path, document)


def sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
    return redact_structure(report)
