"""Profile listing and pin controls."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from perceptshift_api.audit import record_audit
from perceptshift_api.dependencies import DbDep, MutationActorDep, RosDep
from perceptshift_api.errors import ApiError
from perceptshift_api.models import ProfileIndexRecord
from perceptshift_api.schemas import PinRequest, ProfileDetail, ProfileSummary

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _from_index(
    row: ProfileIndexRecord, *, active: str | None, pinned: str | None
) -> ProfileSummary:
    reasons: list[str] = []
    if row.rejection_reasons:
        try:
            parsed = json.loads(row.rejection_reasons)
            if isinstance(parsed, list):
                reasons = [str(item) for item in parsed]
        except json.JSONDecodeError:
            reasons = [row.rejection_reasons]
    model_prefix = row.model_hash[:12] if row.model_hash else None
    return ProfileSummary(
        profile_id=row.profile_id,
        label=row.label,
        model_hash_prefix=model_prefix,
        state=row.state,
        eligible=row.eligible,
        rejection_reasons=reasons,
        certified_quality=_parse_float(row.certified_quality),
        certified_p99_ms=_parse_float(row.certified_p99_ms),
        peak_rss_bytes=_parse_int(row.peak_rss_bytes),
        provider=row.provider,
        active=row.profile_id == active,
        pinned=row.profile_id == pinned,
    )


@router.get("", response_model=list[ProfileSummary])
def list_profiles(ros: RosDep, db: DbDep) -> list[ProfileSummary]:
    live = ros.list_profiles()
    if live:
        return live
    status = ros.runtime_status()
    policy = ros.runtime_policy()
    rows = db.scalars(select(ProfileIndexRecord).order_by(ProfileIndexRecord.profile_id)).all()
    return [
        _from_index(row, active=status.active_profile_id, pinned=policy.pinned_profile_id)
        for row in rows
    ]


@router.get("/{profile_id}", response_model=ProfileDetail)
def get_profile(profile_id: str, ros: RosDep, db: DbDep) -> ProfileDetail:
    live = ros.get_profile(profile_id)
    if live is not None:
        return live
    row = db.scalar(select(ProfileIndexRecord).where(ProfileIndexRecord.profile_id == profile_id))
    if row is None:
        raise ApiError(
            "PROFILE_NOT_FOUND",
            f"Profile '{profile_id}' was not found",
            status_code=404,
            remediation="Load a profile bundle or connect to a live runtime",
        )
    status = ros.runtime_status()
    policy = ros.runtime_policy()
    summary = _from_index(row, active=status.active_profile_id, pinned=policy.pinned_profile_id)
    provenance = {}
    if row.provenance_json:
        try:
            provenance = json.loads(row.provenance_json)
        except json.JSONDecodeError:
            provenance = {}
    return ProfileDetail(**summary.model_dump(), provenance=provenance, attestations={})


@router.post("/{profile_id}/pin")
def pin_profile(
    profile_id: str,
    body: PinRequest,
    request: Request,
    ros: RosDep,
    db: DbDep,
    actor: MutationActorDep,
) -> dict[str, object]:
    _ = body
    try:
        ros.pin_profile(profile_id)
    except ApiError:
        raise
    except RuntimeError as exc:
        raise ApiError(
            "ROS_SERVICE_FAILED",
            str(exc),
            status_code=503,
            remediation="Ensure the ROS runtime node is active and mutation services are enabled",
        ) from exc
    record_audit(
        db,
        actor=actor,
        action="profiles.pin",
        target=profile_id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"pinned_profile_id": profile_id}


@router.delete("/pin")
def clear_pin(
    request: Request,
    ros: RosDep,
    db: DbDep,
    actor: MutationActorDep,
) -> dict[str, object]:
    try:
        ros.clear_pin()
    except ApiError:
        raise
    except RuntimeError as exc:
        raise ApiError(
            "ROS_SERVICE_FAILED",
            str(exc),
            status_code=503,
            remediation="Ensure the ROS runtime node is active and mutation services are enabled",
        ) from exc
    record_audit(
        db,
        actor=actor,
        action="profiles.unpin",
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"pinned_profile_id": None}
