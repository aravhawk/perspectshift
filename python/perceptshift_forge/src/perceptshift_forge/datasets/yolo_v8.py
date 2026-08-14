"""YOLO v8 detection dataset validation (COCO annotation shape)."""

from __future__ import annotations

from pathlib import Path

from perceptshift_forge.datasets import DatasetValidationResult
from perceptshift_forge.datasets.coco import validate_coco_manifest


def validate_yolo_v8_manifest(
    path: Path,
    *,
    allow_symlinks: bool = False,
) -> DatasetValidationResult:
    """Validate a YOLO evaluation set.

    Accepts ``dataset_type`` ``yolo_v8_detection`` (structural) or
    ``coco_detection`` (schema-backed). Annotation layout matches COCO.
    """
    return validate_coco_manifest(path, allow_symlinks=allow_symlinks)
