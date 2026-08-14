"""Build native-worker benchmark streams from validated dataset manifests.

Image path contract (v1):
- Encoded PNG/JPEG/WebP sources are decoded with Pillow during materialization.
- Stream entries for image adapters reference tightly packed raw pixel files
  (``.rgb`` / ``.bgr`` / ``.rgba`` / ``.mono8``), never encoded bytes.
- Each raw_image sample declares ``input_kind=raw_image``, exact width/height,
  stride_bytes, and pixel_format. Payload size must equal stride * height.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_file, write_atomic_json
from perceptshift_common.path_security import resolve_under_root
from perceptshift_common.producer import envelope_fields

_PIXEL_EXT = {
    "rgb8": ".rgb",
    "bgr8": ".bgr",
    "rgba8": ".rgba",
    "bgra8": ".bgra",
    "mono8": ".mono8",
}
_CHANNELS = {
    "rgb8": 3,
    "bgr8": 3,
    "rgba8": 4,
    "bgra8": 4,
    "mono8": 1,
}


def build_benchmark_stream(
    *,
    workspace_root: Path,
    calibration_manifest: dict[str, Any],
    evaluation_manifest: dict[str, Any],
    expected_input: dict[str, Any] | None = None,
    measured_iterations: int = 1,
    pixel_format: str = "rgb8",
) -> Path:
    """Materialize tensors/raw images under the run workspace and write ``bench-stream.json``.

    Never writes production streams that contain only ``synthetic_float_samples``.
    Never marks encoded PNG/JPEG bytes as ``rgb8`` raw pixels.
    """
    stream_dir = workspace_root / "inputs" / "stream"
    stream_dir.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    samples.extend(
        _materialize_split(
            calibration_manifest,
            role="calib",
            stream_dir=stream_dir,
            expected_input=expected_input or {},
            pixel_format=pixel_format,
        )
    )
    samples.extend(
        _materialize_split(
            evaluation_manifest,
            role="eval",
            stream_dir=stream_dir,
            expected_input=expected_input or {},
            pixel_format=pixel_format,
        )
    )
    if not samples:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Benchmark stream has no samples after materialization",
            remediation="Provide non-empty calibration and/or evaluation manifests",
        )
    # Ensure at least measured_iterations eval samples are present by cycling
    # evaluation tensors when the split is smaller than measured count.
    eval_samples = [s for s in samples if s.get("role") == "eval"]
    if measured_iterations > 1 and eval_samples:
        needed = measured_iterations - len(eval_samples)
        for i in range(max(0, needed)):
            base = dict(eval_samples[i % len(eval_samples)])
            base["sample_id"] = f"{base['sample_id']}#iter{i + 1}"
            samples.append(base)

    document = envelope_fields(document_type="perceptshift.benchmark_stream")
    document.update(
        {
            "schema_version": "1.0",
            "samples": samples,
            "sample_count": len(samples),
        }
    )
    out = workspace_root / "inputs" / "bench-stream.json"
    write_atomic_json(out, document)
    return out


def load_stream_tensors(stream_path: Path, *, role: str | None = None) -> list[dict[str, Any]]:
    doc = json.loads(stream_path.read_text(encoding="utf-8"))
    samples = doc.get("samples") or []
    # Native worker resolves relative paths against the stream file parent (inputs/).
    stream_base = stream_path.resolve().parent
    workspace = stream_base.parent
    loaded: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        if role is not None and sample.get("role") != role:
            continue
        rel = sample.get("tensor_path")
        if not isinstance(rel, str):
            continue
        path = Path(rel)
        if not path.is_absolute():
            candidate = stream_base / rel
            if not candidate.is_file() and rel.startswith("inputs/"):
                candidate = workspace / rel
            path = candidate
        if not path.is_file():
            raise PerceptShiftError(
                code=ErrorCode.DATASET_INVALID,
                message=f"Stream tensor missing: {rel}",
            )
        array = (
            np.load(str(path))
            if path.suffix == ".npy"
            else np.fromfile(str(path), dtype=np.float32)
        )
        shape = sample.get("shape")
        if path.suffix != ".npy" and isinstance(shape, list) and shape:
            array = np.asarray(array).reshape([int(x) for x in shape])
        entry = {
            "sample_id": sample.get("sample_id"),
            "role": sample.get("role"),
            "tensor": np.asarray(array, dtype=np.float32),
            "tensor_path": rel,
            "label": sample.get("label"),
            "sha256": sample.get("sha256") or sha256_file(path),
        }
        loaded.append(entry)
    return loaded


def materialize_raw_image(
    source: Path,
    dest: Path,
    *,
    pixel_format: str = "rgb8",
) -> dict[str, Any]:
    """Decode an encoded image to a tightly packed raw pixel file.

    Returns metadata: width, height, stride_bytes, pixel_format, byte_size.
    Rejects unknown formats. Does not resize — preserves source geometry.
    """
    if pixel_format not in _CHANNELS:
        raise PerceptShiftError(
            code=ErrorCode.INPUT_UNSUPPORTED,
            message=f"unsupported pixel_format for raw materialization: {pixel_format}",
        )
    channels = _CHANNELS[pixel_format]
    with Image.open(source) as img:
        if pixel_format == "mono8":
            converted = img.convert("L")
            array = np.asarray(converted, dtype=np.uint8)
            if array.ndim != 2:
                raise PerceptShiftError(
                    code=ErrorCode.DATASET_INVALID,
                    message="mono8 materialization produced non-2D array",
                )
            height, width = int(array.shape[0]), int(array.shape[1])
            packed = np.ascontiguousarray(array)
        elif pixel_format in {"rgb8", "bgr8"}:
            converted = img.convert("RGB")
            array = np.asarray(converted, dtype=np.uint8)
            if pixel_format == "bgr8":
                array = array[:, :, ::-1]
            height, width = int(array.shape[0]), int(array.shape[1])
            packed = np.ascontiguousarray(array)
        else:  # rgba8 / bgra8
            converted = img.convert("RGBA")
            array = np.asarray(converted, dtype=np.uint8)
            if pixel_format == "bgra8":
                array = array[:, :, [2, 1, 0, 3]]
            height, width = int(array.shape[0]), int(array.shape[1])
            packed = np.ascontiguousarray(array)

    stride = width * channels
    expected = stride * height
    payload = packed.tobytes(order="C")
    if len(payload) != expected:
        raise PerceptShiftError(
            code=ErrorCode.INTERNAL_INVARIANT_FAILED,
            message=(
                f"raw pixel payload size {len(payload)} != stride*height {expected} "
                f"for {pixel_format} {width}x{height}"
            ),
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return {
        "width": width,
        "height": height,
        "stride_bytes": stride,
        "pixel_format": pixel_format,
        "byte_size": expected,
    }


def _write_raw_f32(path: Path, array: np.ndarray) -> None:
    """Write float32 payload without a container header (native worker contract)."""
    path.write_bytes(np.asarray(array, dtype=np.float32).tobytes(order="C"))


def _materialize_split(
    manifest: dict[str, Any],
    *,
    role: str,
    stream_dir: Path,
    expected_input: dict[str, Any],
    pixel_format: str = "rgb8",
) -> list[dict[str, Any]]:
    dataset_type = manifest.get("dataset_type")
    root = Path(manifest["root"])
    samples: list[dict[str, Any]] = []

    if dataset_type == "raw_tensor":
        items = manifest.get("items") or []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path") or item.get("tensor_path") or "")
            resolved = resolve_under_root(root, rel, field="item.path")
            sample_id = str(item.get("item_id") or item.get("sample_id") or f"{role}-{index}")
            dest = stream_dir / role
            dest.mkdir(parents=True, exist_ok=True)
            out_path = dest / f"{_safe_id(sample_id)}.f32"
            array = _load_tensor_file(resolved)
            array = _maybe_reshape(array, expected_input)
            _write_raw_f32(out_path, array)
            rel_workspace = f"stream/{role}/{out_path.name}"
            entry: dict[str, Any] = {
                "sample_id": sample_id,
                "role": role,
                "input_kind": "raw_tensor",
                "tensor_path": rel_workspace,
                "sha256": sha256_file(out_path),
                "shape": list(array.shape),
                "dtype": "float32",
            }
            if "label" in item:
                entry["label"] = item["label"]
            samples.append(entry)
        return samples

    if dataset_type == "image_classification_manifest":
        items = manifest.get("items") or []
        resize = _resolve_resize(manifest, expected_input)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path", ""))
            resolved = resolve_under_root(root, rel, field="item.path")
            sample_id = str(item.get("item_id") or f"{role}-{index}")
            dest = stream_dir / role
            dest.mkdir(parents=True, exist_ok=True)
            safe = _safe_id(sample_id)
            # Provenance: keep encoded original for evidence only.
            provenance_name = f"{safe}.source{resolved.suffix.lower() or '.png'}"
            provenance_out = dest / provenance_name
            provenance_out.write_bytes(resolved.read_bytes())

            ext = _PIXEL_EXT.get(pixel_format, ".rgb")
            raw_name = f"{safe}{ext}"
            raw_out = dest / raw_name
            meta = materialize_raw_image(resolved, raw_out, pixel_format=pixel_format)
            image_rel = f"stream/{role}/{raw_name}"

            # Optional float tensor for Python-side helpers (never used to bypass
            # native image preprocess for image adapters — see input_kind).
            array = _image_to_nchw(resolved, size=resize)
            array = _maybe_reshape(array, expected_input)
            tensor_out = dest / f"{safe}.f32"
            _write_raw_f32(tensor_out, array)

            entry = {
                "sample_id": sample_id,
                "role": role,
                "input_kind": "raw_image",
                "image_path": image_rel,
                # Auxiliary float tensor for Python label/debug helpers only.
                # Native image adapters must use image_path (input_kind=raw_image).
                "tensor_path": f"stream/{role}/{tensor_out.name}",
                "provenance_encoded_path": f"stream/{role}/{provenance_name}",
                "source_path": str(resolved),
                "sha256": sha256_file(raw_out),
                "label": item.get("class_id"),
                "pixel_format": meta["pixel_format"],
                "width": meta["width"],
                "height": meta["height"],
                "source_width": meta["width"],
                "source_height": meta["height"],
                "stride_bytes": meta["stride_bytes"],
                "byte_size": meta["byte_size"],
                "shape": list(array.shape),
                "dtype": "float32",
            }
            if resize is not None:
                entry["expected_resize"] = list(resize)
            samples.append(entry)
        return samples

    if dataset_type in {"coco_detection", "yolo_v8_detection"}:
        annotation_rel = manifest.get("annotation_path")
        if not isinstance(annotation_rel, str):
            raise PerceptShiftError(
                code=ErrorCode.DATASET_INVALID,
                message="Detection manifest missing annotation_path",
            )
        annotation_path = resolve_under_root(root, annotation_rel, field="annotation_path")
        annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
        images = annotations.get("images") or []
        resize = _resolve_resize(manifest, expected_input)
        for index, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            file_name = image.get("file_name")
            if not isinstance(file_name, str):
                continue
            resolved = resolve_under_root(root, file_name, field="image.file_name")
            sample_id = str(image.get("id") or f"{role}-{index}")
            dest = stream_dir / role
            dest.mkdir(parents=True, exist_ok=True)
            safe = _safe_id(str(sample_id))
            provenance_name = f"{safe}.source{resolved.suffix.lower() or '.png'}"
            (dest / provenance_name).write_bytes(resolved.read_bytes())
            ext = _PIXEL_EXT.get(pixel_format, ".rgb")
            raw_name = f"{safe}{ext}"
            raw_out = dest / raw_name
            meta = materialize_raw_image(resolved, raw_out, pixel_format=pixel_format)
            array = _image_to_nchw(resolved, size=resize)
            array = _maybe_reshape(array, expected_input)
            tensor_out = dest / f"{safe}.f32"
            _write_raw_f32(tensor_out, array)
            samples.append(
                {
                    "sample_id": str(sample_id),
                    "role": role,
                    "input_kind": "raw_image",
                    "image_path": f"stream/{role}/{raw_name}",
                    "tensor_path": f"stream/{role}/{tensor_out.name}",
                    "provenance_encoded_path": f"stream/{role}/{provenance_name}",
                    "source_path": str(resolved),
                    "sha256": sha256_file(raw_out),
                    "label": None,
                    "image_id": image.get("id"),
                    "pixel_format": meta["pixel_format"],
                    "width": meta["width"],
                    "height": meta["height"],
                    "source_width": meta["width"],
                    "source_height": meta["height"],
                    "stride_bytes": meta["stride_bytes"],
                    "byte_size": meta["byte_size"],
                    "expected_resize": list(resize) if resize is not None else None,
                    "shape": list(array.shape),
                    "dtype": "float32",
                }
            )
        return samples

    raise PerceptShiftError(
        code=ErrorCode.DATASET_INVALID,
        message=f"Unsupported dataset_type for benchmark stream: {dataset_type}",
    )


def _safe_id(sample_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in sample_id)[:120]


def _resolve_resize(
    manifest: dict[str, Any],
    expected_input: dict[str, Any],
) -> tuple[int, int] | None:
    shape = expected_input.get("shape") or expected_input.get("input_shape")
    if isinstance(shape, list) and len(shape) >= 4:
        # NCHW → (width, height) for PIL resize
        return int(shape[-1]), int(shape[-2])
    contract = manifest.get("preprocess_contract") or {}
    if "input_width" in contract and "input_height" in contract:
        return int(contract["input_width"]), int(contract["input_height"])
    if "width" in contract and "height" in contract:
        return int(contract["width"]), int(contract["height"])
    resize = contract.get("resize")
    if isinstance(resize, list) and len(resize) == 2:
        return int(resize[0]), int(resize[1])
    return None


def _image_to_nchw(path: Path, *, size: tuple[int, int] | None) -> np.ndarray:
    with Image.open(path) as img:
        image = img.convert("RGB")
        if size is not None:
            image = image.resize(size, Image.Resampling.BILINEAR)
        array = np.asarray(image, dtype=np.float32) / 255.0
    chw = np.transpose(array, (2, 0, 1))
    return np.expand_dims(chw, axis=0)


def _load_tensor_file(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.asarray(np.load(str(path)))
    if suffix in {".npz", ".bin", ".f32"}:
        return np.fromfile(str(path), dtype=np.float32)
    # Allow image paths inside a raw_tensor item list (decoded to float tensor only).
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
        return _image_to_nchw(path, size=None)
    raise PerceptShiftError(
        code=ErrorCode.DATASET_INVALID,
        message=f"Unsupported tensor file type: {path.suffix}",
        details={"path": str(path)},
    )


def _maybe_reshape(array: np.ndarray, expected_input: dict[str, Any]) -> np.ndarray:
    """Require exact element counts for fixed shapes; never silently pad/truncate."""
    shape = expected_input.get("shape") or expected_input.get("input_shape")
    arr = np.asarray(array, dtype=np.float32)
    if not isinstance(shape, list) or not shape:
        return arr
    target: list[int] = []
    dynamic_idxs: list[int] = []
    for idx, dim in enumerate(shape):
        if isinstance(dim, int) and dim > 0:
            target.append(dim)
        else:
            dynamic_idxs.append(idx)
            target.append(-1)
    if not dynamic_idxs:
        needed = int(np.prod(target))
        if arr.size != needed:
            raise PerceptShiftError(
                code=ErrorCode.MODEL_TENSOR_MISMATCH,
                message=(
                    f"Tensor element count {arr.size} does not match fixed expected shape "
                    f"{target} ({needed}); refusing silent pad/truncate"
                ),
            )
        return arr.reshape(target)
    if len(dynamic_idxs) != 1:
        raise PerceptShiftError(
            code=ErrorCode.MODEL_TENSOR_MISMATCH,
            message="Ambiguous unresolved dynamic dimensions; refusing to invent shape",
        )
    known = 1
    for dim in target:
        if dim > 0:
            known *= dim
    if known <= 0 or (arr.size % known) != 0:
        raise PerceptShiftError(
            code=ErrorCode.MODEL_TENSOR_MISMATCH,
            message="Cannot resolve dynamic dimension from concrete tensor size",
        )
    resolved = list(target)
    resolved[dynamic_idxs[0]] = int(arr.size // known)
    return arr.reshape(resolved)
