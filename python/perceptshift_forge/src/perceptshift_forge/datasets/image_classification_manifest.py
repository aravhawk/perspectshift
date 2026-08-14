"""Image classification manifest reader and validator."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.datasets import (
    DatasetValidationResult,
    hash_file_under_root,
    load_and_validate_manifest,
)


def validate_image_classification_manifest(
    path: Path,
    *,
    allow_symlinks: bool = False,
) -> DatasetValidationResult:
    manifest = load_and_validate_manifest(path)
    if manifest.get("dataset_type") != "image_classification_manifest":
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Expected dataset_type image_classification_manifest",
            details={"dataset_type": manifest.get("dataset_type")},
        )
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Classification manifest requires a non-empty items array",
        )

    root = Path(manifest["root"])
    content_hashes: list[str] = []
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    class_counter: Counter[str] = Counter()
    missing = 0
    seen: dict[str, str] = {}

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(
                {
                    "reason_code": "dataset.invalid_item",
                    "message": f"Item {index} is not an object",
                }
            )
            continue
        rel = str(item.get("path", ""))
        class_id = item.get("class_id")
        try:
            _resolved, digest = hash_file_under_root(root, rel, allow_symlinks=allow_symlinks)
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
            continue
        if digest in seen:
            warnings.append(
                {
                    "reason_code": str(ReasonCode.DATASET_DUPLICATE),
                    "message": f"Duplicate content hash for {rel} and {seen[digest]}",
                }
            )
        else:
            seen[digest] = rel
        content_hashes.append(digest)
        class_counter[str(class_id)] += 1

    duplicate_count = len(content_hashes) - len(set(content_hashes))
    result = DatasetValidationResult(
        manifest=manifest,
        manifest_hash=sha256_canonical(manifest),
        content_hashes=sorted(content_hashes),
        item_count=len(items),
        missing_count=missing,
        duplicate_count=duplicate_count,
        class_counts=dict(sorted(class_counter.items())),
        warnings=warnings,
        errors=errors,
    )
    return result
