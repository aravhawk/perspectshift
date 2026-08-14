"""Run index and artifact access endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import select

from perceptshift_api.dependencies import DbDep, SettingsDep
from perceptshift_api.errors import ApiError
from perceptshift_api.models import ArtifactRecord, CandidateRecord, RunRecord
from perceptshift_api.paths import (
    content_disposition_attachment,
    ensure_within_roots,
    safe_display_path,
)
from perceptshift_api.schemas import CandidateSummary, RunDetail, RunSummary

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_summary(row: RunRecord) -> RunSummary:
    return RunSummary(
        run_id=row.run_id,
        valid=row.valid,
        host=row.host,
        model_hash=row.model_hash,
        data_hash=row.data_hash,
        candidate_count=row.candidate_count,
        quality_summary=row.quality_summary,
        latency_summary=row.latency_summary,
        import_status=row.import_status,
        pinned=row.pinned,
        created_at=row.created_at,
    )


@router.get("", response_model=list[RunSummary])
def list_runs(db: DbDep, limit: int = 100) -> list[RunSummary]:
    clamped = max(1, min(limit, 500))
    rows = db.scalars(select(RunRecord).order_by(RunRecord.created_at.desc()).limit(clamped)).all()
    return [_run_summary(row) for row in rows]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: DbDep) -> RunDetail:
    row = db.scalar(select(RunRecord).where(RunRecord.run_id == run_id))
    if row is None:
        raise ApiError(
            "RUN_NOT_FOUND",
            f"Run '{run_id}' was not found",
            status_code=404,
            remediation="Import or index a forge run into the artifact store",
        )
    summary = _run_summary(row)
    return RunDetail(
        **summary.model_dump(), workspace_display=safe_display_path(Path(row.workspace_path))
    )


@router.get("/{run_id}/summary", response_model=RunDetail)
def get_run_summary(run_id: str, db: DbDep) -> RunDetail:
    return get_run(run_id, db)


@router.get("/{run_id}/candidates", response_model=list[CandidateSummary])
def list_candidates(run_id: str, db: DbDep) -> list[CandidateSummary]:
    run = db.scalar(select(RunRecord).where(RunRecord.run_id == run_id))
    if run is None:
        raise ApiError("RUN_NOT_FOUND", f"Run '{run_id}' was not found", status_code=404)
    rows = db.scalars(
        select(CandidateRecord)
        .where(CandidateRecord.run_id == run_id)
        .order_by(CandidateRecord.candidate_id)
    ).all()
    results: list[CandidateSummary] = []
    for row in rows:
        summary: dict = {}
        if row.summary_json:
            try:
                summary = json.loads(row.summary_json)
            except json.JSONDecodeError:
                summary = {}
        quality = None
        latency = None
        if row.quality_value is not None:
            try:
                quality = float(row.quality_value)
            except ValueError:
                quality = None
        if row.latency_p99_ms is not None:
            try:
                latency = float(row.latency_p99_ms)
            except ValueError:
                latency = None
        results.append(
            CandidateSummary(
                candidate_id=row.candidate_id,
                profile_id=row.profile_id,
                valid=row.valid,
                quality_value=quality,
                latency_p99_ms=latency,
                summary=summary,
            )
        )
    return results


@router.get("/{run_id}/artifacts/{artifact_id}")
def get_artifact(
    run_id: str,
    artifact_id: str,
    db: DbDep,
    settings: SettingsDep,
) -> FileResponse:
    if "/" in artifact_id or "\\" in artifact_id or ".." in artifact_id:
        raise ApiError(
            "PATH_TRAVERSAL",
            "Invalid artifact identifier",
            status_code=400,
        )
    row = db.scalar(
        select(ArtifactRecord).where(
            ArtifactRecord.run_id == run_id,
            ArtifactRecord.artifact_id == artifact_id,
        )
    )
    if row is None:
        raise ApiError(
            "ARTIFACT_NOT_FOUND",
            f"Artifact '{artifact_id}' was not found for run '{run_id}'",
            status_code=404,
        )
    roots = settings.resolved_artifact_roots()
    path = ensure_within_roots(Path(row.path), roots, follow_symlinks=True)
    if not path.is_file():
        raise ApiError(
            "ARTIFACT_MISSING",
            "Indexed artifact path is missing on disk",
            status_code=404,
        )
    # Symlink escape check: resolved path must still be under roots.
    ensure_within_roots(path, roots, follow_symlinks=True)
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition_attachment(path.name),
            "X-Content-Type-Options": "nosniff",
        },
    )
