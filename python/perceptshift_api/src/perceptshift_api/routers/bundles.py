"""Bundle inspection and verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Request

from perceptshift_api.audit import record_audit
from perceptshift_api.dependencies import DbDep, MutationActorDep, SettingsDep
from perceptshift_api.errors import ApiError
from perceptshift_api.paths import ensure_within_roots, safe_display_path
from perceptshift_api.schemas import (
    BundleInfo,
    BundleVerifyRequest,
    BundleVerifyResult,
    UnavailableField,
)

router = APIRouter(prefix="/bundles", tags=["bundles"])


def _find_current_bundle(roots: list[Path]) -> Path | None:
    for root in roots:
        candidate = root / "current" / "bundle.manifest.json"
        if candidate.is_file():
            return candidate
        # Also accept a direct manifest at root/current.json
        alt = root / "current.json"
        if alt.is_file():
            return alt
    return None


def _load_bundle_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(
            "BUNDLE_INVALID",
            "Unable to read bundle manifest",
            status_code=400,
            details={"reason": str(exc)},
        ) from exc


@router.get("/current", response_model=BundleInfo)
def current_bundle(settings: SettingsDep) -> BundleInfo:
    roots = settings.resolved_artifact_roots()
    path = _find_current_bundle(roots)
    if path is None:
        return BundleInfo(
            integrity_status="unavailable",
            signature_status="unavailable",
            unavailable={
                "bundle": UnavailableField(
                    reason_code="BUNDLE_NOT_FOUND",
                    message="No current profile bundle is registered in artifact roots",
                )
            },
        )
    data = _load_bundle_manifest(path)
    profiles = []
    raw_profiles = data.get("profiles") or []
    if isinstance(raw_profiles, list):
        for item in raw_profiles:
            if isinstance(item, dict) and "profile_id" in item:
                profiles.append(str(item["profile_id"]))
            elif isinstance(item, str):
                profiles.append(item)
    file_hashes: dict[str, str] = {}
    files = data.get("files") or {}
    if isinstance(files, dict):
        for name, meta in files.items():
            if isinstance(meta, dict) and "sha256" in meta:
                file_hashes[str(name)] = str(meta["sha256"])
            elif isinstance(meta, str):
                file_hashes[str(name)] = meta
    return BundleInfo(
        bundle_id=data.get("bundle_id"),
        schema_version=data.get("schema_version"),
        product_version=data.get("product_version"),
        integrity_status="manifest_present",
        signature_status="not_verified",
        path_display=safe_display_path(path),
        profiles=profiles,
        file_hashes=file_hashes,
        provenance={
            "calibration_dataset_hash": data.get("calibration_dataset_hash"),
            "evaluation_dataset_hash": data.get("evaluation_dataset_hash"),
            "host_fingerprint_ref": data.get("host_fingerprint_ref"),
        },
    )


@router.post("/verify", response_model=BundleVerifyResult)
def verify_bundle(
    body: BundleVerifyRequest,
    request: Request,
    settings: SettingsDep,
    db: DbDep,
    actor: MutationActorDep,
) -> BundleVerifyResult:
    roots = settings.resolved_artifact_roots()
    path = ensure_within_roots(Path(body.path), roots, follow_symlinks=True)
    if not path.is_file():
        raise ApiError(
            "BUNDLE_NOT_FOUND",
            "Bundle path does not exist or is not a file",
            status_code=404,
        )
    data = _load_bundle_manifest(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    details = {
        "manifest_sha256": digest,
        "bundle_id": data.get("bundle_id"),
        "schema_version": data.get("schema_version"),
        "file_count": len(data.get("files") or {}),
    }
    record_audit(
        db,
        actor=actor,
        action="bundles.verify",
        target=safe_display_path(path),
        details={"manifest_sha256": digest},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return BundleVerifyResult(
        path_display=safe_display_path(path),
        integrity_status="hash_computed",
        signature_status="not_verified",
        details=details,
    )
