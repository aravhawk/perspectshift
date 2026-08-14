"""Dispatch dataset validation by dataset_type."""

from __future__ import annotations

from pathlib import Path

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.schema import load_json_document
from perceptshift_forge.datasets import DatasetValidationResult
from perceptshift_forge.datasets.coco import validate_coco_manifest
from perceptshift_forge.datasets.image_classification_manifest import (
    validate_image_classification_manifest,
)
from perceptshift_forge.datasets.raw_tensor import validate_raw_tensor_manifest
from perceptshift_forge.datasets.yolo_v8 import validate_yolo_v8_manifest


def validate_dataset_manifest(
    path: Path,
    *,
    allow_symlinks: bool = False,
) -> DatasetValidationResult:
    document = load_json_document(path)
    dataset_type = document.get("dataset_type")
    if dataset_type == "image_classification_manifest":
        return validate_image_classification_manifest(path, allow_symlinks=allow_symlinks)
    if dataset_type == "coco_detection":
        return validate_coco_manifest(path, allow_symlinks=allow_symlinks)
    if dataset_type == "yolo_v8_detection":
        return validate_yolo_v8_manifest(path, allow_symlinks=allow_symlinks)
    if dataset_type == "raw_tensor":
        return validate_raw_tensor_manifest(path, allow_symlinks=allow_symlinks)
    raise PerceptShiftError(
        code=ErrorCode.DATASET_INVALID,
        message=f"Unsupported dataset_type: {dataset_type}",
    )
