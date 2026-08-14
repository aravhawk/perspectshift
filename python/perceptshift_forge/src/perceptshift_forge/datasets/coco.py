"""COCO detection dataset manifest validation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical, sha256_file
from perceptshift_common.path_security import resolve_under_root
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.datasets import (
    DatasetValidationResult,
    hash_file_under_root,
    load_and_validate_manifest,
)


def validate_coco_manifest(
    path: Path,
    *,
    allow_symlinks: bool = False,
) -> DatasetValidationResult:
    from perceptshift_common.schema import load_json_document

    peek = load_json_document(path)
    dataset_type = peek.get("dataset_type")
    if dataset_type == "yolo_v8_detection":
        # Alias pending schema enum update; validate structure without enum reject.
        manifest = peek
    else:
        manifest = load_and_validate_manifest(path)
    if manifest.get("dataset_type") not in {"coco_detection", "yolo_v8_detection"}:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Expected dataset_type coco_detection or yolo_v8_detection",
            details={"dataset_type": manifest.get("dataset_type")},
        )

    root = Path(manifest["root"])
    annotation_rel = manifest.get("annotation_path")
    if not isinstance(annotation_rel, str) or not annotation_rel:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="COCO manifest requires annotation_path",
        )

    annotation_path = resolve_under_root(
        root,
        annotation_rel,
        allow_symlinks=allow_symlinks,
        field="annotation_path",
    )
    if not annotation_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message=f"COCO annotation file missing: {annotation_rel}",
            details={"reason_code": ReasonCode.DATASET_MISSING_FILE},
        )

    try:
        annotations: dict[str, Any] = json.loads(annotation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Failed to parse COCO annotation JSON",
            cause=exc,
        ) from exc

    images = annotations.get("images")
    if not isinstance(images, list):
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="COCO annotations missing images array",
        )

    content_hashes: list[str] = []
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    missing = 0
    class_counter: Counter[str] = Counter()
    allowlist = set(manifest.get("category_allowlist") or [])

    anns = annotations.get("annotations")
    if isinstance(anns, list):
        for ann in anns:
            if not isinstance(ann, dict):
                continue
            cat = ann.get("category_id")
            if allowlist and cat not in allowlist:
                continue
            if manifest.get("crowd_treatment") == "exclude" and ann.get("iscrowd"):
                continue
            class_counter[str(cat)] += 1

    for image in images:
        if not isinstance(image, dict):
            continue
        file_name = image.get("file_name")
        if not isinstance(file_name, str):
            errors.append(
                {
                    "reason_code": str(ReasonCode.DATASET_MISSING_FILE),
                    "message": "COCO image entry missing file_name",
                }
            )
            missing += 1
            continue
        try:
            _resolved, digest = hash_file_under_root(root, file_name, allow_symlinks=allow_symlinks)
            content_hashes.append(digest)
        except PerceptShiftError as exc:
            missing += 1
            errors.append(
                {
                    "reason_code": str(
                        (exc.details or {}).get("reason_code", ReasonCode.DATASET_MISSING_FILE)
                    ),
                    "message": exc.message,
                }
            )

    annotation_hash = sha256_file(annotation_path)
    content_hashes.append(f"annotation:{annotation_hash}")
    duplicate_count = len(content_hashes) - len(set(content_hashes))

    return DatasetValidationResult(
        manifest=manifest,
        manifest_hash=sha256_canonical(manifest),
        content_hashes=sorted(content_hashes),
        item_count=len(images),
        missing_count=missing,
        duplicate_count=duplicate_count,
        class_counts=dict(sorted(class_counter.items())),
        warnings=warnings,
        errors=errors,
    )
