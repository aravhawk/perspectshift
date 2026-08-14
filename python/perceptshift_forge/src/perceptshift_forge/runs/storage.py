"""Run index storage under XDG data directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perceptshift_common.hashing import write_atomic_json
from perceptshift_common.paths import ensure_dir, runs_index_dir
from perceptshift_common.producer import utc_now_rfc3339


def index_path() -> Path:
    return ensure_dir(runs_index_dir()) / "index.json"


def load_index() -> dict[str, Any]:
    path = index_path()
    if not path.is_file():
        return {"runs": [], "updated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def index_run(run_root: Path, run_doc: dict[str, Any]) -> None:
    index = load_index()
    runs = [r for r in index.get("runs", []) if r.get("run_id") != run_doc.get("run_id")]
    runs.append(
        {
            "run_id": run_doc.get("run_id"),
            "root": str(run_root.resolve()),
            "status": run_doc.get("status"),
            "config_hash": run_doc.get("config_hash"),
            "product_version": run_doc.get("product_version"),
            "indexed_at": utc_now_rfc3339(),
        }
    )
    runs.sort(key=lambda r: str(r.get("run_id", "")), reverse=True)
    write_atomic_json(index_path(), {"runs": runs, "updated_at": utc_now_rfc3339()})


def list_runs() -> list[dict[str, Any]]:
    return list(load_index().get("runs", []))
