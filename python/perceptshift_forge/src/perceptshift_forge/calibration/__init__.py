"""Calibration sample loading helpers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.path_security import resolve_under_root
from perceptshift_forge.datasets.image_classification_manifest import (
    validate_image_classification_manifest,
)


@dataclass(slots=True)
class CalibrationBatch:
    sample_count: int
    dataset_hash: str
    tensors: list[dict[str, np.ndarray]]


def _load_image_chw(path: Path, *, size: tuple[int, int] | None = None) -> np.ndarray:
    with Image.open(path) as img:
        image = img.convert("RGB")
        if size is not None:
            image = image.resize(size, Image.Resampling.BILINEAR)
        array = np.asarray(image, dtype=np.float32) / 255.0
    return np.transpose(array, (2, 0, 1))


def iter_classification_calibration_tensors(
    manifest_path: Path,
    *,
    input_name: str = "input",
    sample_limit: int | None = None,
    image_size: tuple[int, int] | None = None,
    allow_symlinks: bool = False,
) -> CalibrationBatch:
    result = validate_image_classification_manifest(manifest_path, allow_symlinks=allow_symlinks)
    if not result.ok:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Calibration dataset validation failed",
            details={"errors": result.errors},
        )
    root = Path(result.manifest["root"])
    items = result.manifest.get("items") or []
    tensors: list[dict[str, np.ndarray]] = []
    for item in items:
        if sample_limit is not None and len(tensors) >= sample_limit:
            break
        if not isinstance(item, dict):
            continue
        resolved = resolve_under_root(
            root, str(item["path"]), allow_symlinks=allow_symlinks, field="item.path"
        )
        try:
            tensor = _load_image_chw(resolved, size=image_size)
        except OSError as exc:
            raise PerceptShiftError(
                code=ErrorCode.DATASET_INVALID,
                message=f"Failed to decode calibration image: {item['path']}",
                cause=exc,
            ) from exc
        tensors.append({input_name: np.expand_dims(tensor, axis=0)})
    if not tensors:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="No calibration tensors could be loaded",
        )
    return CalibrationBatch(
        sample_count=len(tensors),
        dataset_hash=result.manifest_hash,
        tensors=tensors,
    )


def stream_paths(paths: list[Path]) -> Iterator[Path]:
    yield from paths
