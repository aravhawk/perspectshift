"""Dataset validation utilities shared by readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical, sha256_file
from perceptshift_common.path_security import resolve_under_root
from perceptshift_common.producer import envelope_fields
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_common.schema import load_json_document, validate_document


@dataclass(slots=True)
class DatasetValidationResult:
    manifest: dict[str, Any]
    manifest_hash: str
    content_hashes: list[str]
    item_count: int
    missing_count: int
    duplicate_count: int
    class_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def load_and_validate_manifest(path: Path) -> dict[str, Any]:
    document = load_json_document(path)
    return validate_document(document, "dataset_manifest")


def assert_split_isolation(
    calibration: DatasetValidationResult,
    evaluation: DatasetValidationResult,
    *,
    prohibit_duplicates: bool,
) -> None:
    if calibration.manifest_hash == evaluation.manifest_hash:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_LEAKAGE,
            message="Calibration and evaluation manifests are identical",
            remediation="Use distinct calibration and evaluation manifests",
        )
    if not prohibit_duplicates:
        return
    cal = set(calibration.content_hashes)
    overlap = sorted(cal.intersection(evaluation.content_hashes))
    if overlap:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_LEAKAGE,
            message="Cross-split duplicate content detected",
            remediation="Remove overlapping samples or disable prohibit_cross_split_duplicates",
            details={
                "overlap_count": len(overlap),
                "reason_code": ReasonCode.DATASET_CROSS_SPLIT_LEAKAGE,
                "sample_hashes": overlap[:16],
            },
        )


def hash_file_under_root(
    root: Path,
    relative: str,
    *,
    allow_symlinks: bool = False,
) -> tuple[Path, str]:
    resolved = resolve_under_root(
        root,
        relative,
        allow_symlinks=allow_symlinks,
        field="item.path",
    )
    if not resolved.is_file():
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message=f"Dataset item missing or unreadable: {relative}",
            details={"reason_code": ReasonCode.DATASET_MISSING_FILE},
        )
    return resolved, sha256_file(resolved)


def summarize_result(result: DatasetValidationResult) -> dict[str, Any]:
    payload = envelope_fields(document_type="perceptshift.dataset_summary")
    payload.update(
        {
            "manifest_hash": result.manifest_hash,
            "item_count": result.item_count,
            "missing_count": result.missing_count,
            "duplicate_count": result.duplicate_count,
            "class_counts": result.class_counts,
            "content_hash_count": len(result.content_hashes),
            "ok": result.ok,
            "warnings": result.warnings,
            "errors": result.errors,
        }
    )
    return payload


def content_hash_list_digest(hashes: list[str]) -> str:
    return sha256_canonical(sorted(hashes))
