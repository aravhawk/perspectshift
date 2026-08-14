"""Raw-tensor dataset manifest validation (software contract).

Coordinator schema request: add ``raw_tensor`` to dataset_manifest
``dataset_type`` enum and allow item fields ``path`` (tensor file), optional
``label`` / ``expected_output_path``, and optional ``shape`` / ``dtype``.
Until the schema enum is updated, structural validation is performed here
without ``validate_document(..., "dataset_manifest")``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_common.schema import load_json_document
from perceptshift_forge.datasets import (
    DatasetValidationResult,
    hash_file_under_root,
)

_REQUIRED_TOP = (
    "schema_version",
    "document_type",
    "dataset_type",
    "dataset_name",
    "root",
    "license_reference",
    "split_name",
    "preprocess_contract",
)


def validate_raw_tensor_manifest(
    path: Path,
    *,
    allow_symlinks: bool = False,
) -> DatasetValidationResult:
    manifest = load_json_document(path)
    if manifest.get("dataset_type") != "raw_tensor":
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Expected dataset_type raw_tensor",
            details={"dataset_type": manifest.get("dataset_type")},
        )
    _assert_envelope(manifest)
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="raw_tensor manifest requires a non-empty items array",
        )

    root = Path(manifest["root"])
    content_hashes: list[str] = []
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    class_counter: Counter[str] = Counter()
    missing = 0
    seen: dict[str, str] = {}
    seen_ids: set[str] = set()

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(
                {
                    "reason_code": "dataset.invalid_item",
                    "message": f"Item {index} is not an object",
                }
            )
            continue
        rel = str(item.get("path") or item.get("tensor_path") or "")
        if not rel:
            errors.append(
                {
                    "reason_code": "dataset.invalid_item",
                    "message": f"Item {index} missing path/tensor_path",
                }
            )
            continue
        sample_id = str(item.get("item_id") or item.get("sample_id") or rel)
        if sample_id in seen_ids:
            errors.append(
                {
                    "reason_code": str(ReasonCode.DATASET_DUPLICATE),
                    "message": f"Duplicate sample_id: {sample_id}",
                }
            )
            continue
        seen_ids.add(sample_id)
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
        if "label" in item:
            class_counter[str(item["label"])] += 1
        expected = item.get("expected_output_path")
        if isinstance(expected, str) and expected:
            try:
                _out, out_digest = hash_file_under_root(
                    root, expected, allow_symlinks=allow_symlinks
                )
                content_hashes.append(f"expected:{out_digest}")
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

    duplicate_count = len(content_hashes) - len(set(content_hashes))
    return DatasetValidationResult(
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


def _assert_envelope(manifest: dict[str, Any]) -> None:
    for key in _REQUIRED_TOP:
        if key not in manifest:
            raise PerceptShiftError(
                code=ErrorCode.DATASET_INVALID,
                message=f"raw_tensor manifest missing required field: {key}",
            )
    if manifest.get("schema_version") != "1.0":
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="raw_tensor schema_version must be 1.0",
        )
    if manifest.get("document_type") != "perceptshift.dataset_manifest":
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="document_type must be perceptshift.dataset_manifest",
        )
