"""Canonical preprocessing-contract builder shared by Forge candidates and datasets.

Precedence (documented and tested):
1. Explicit Forge/model preprocessing configuration (`model.preprocess` or
   `model.preprocess_contract`).
2. Dataset preprocessing contract when compatible.
3. Fixed model input shape/layout where safely inferable from `expected_input`.
4. Safe product defaults only for fields whose meaning is unambiguous
   (resize_mode=stretch, resize_interpolation=bilinear, output_dtype=float32,
   accepted_source_formats, source_color_handling, backend when requested).

Semantic normalization values (mean/std/scale/layout/width/height) are never
invented for arbitrary external models — missing values raise CONFIG_INVALID.
"""

from __future__ import annotations

from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.schema import validate_document

# Unambiguous v1 defaults — not semantic normalization.
_DEFAULT_ACCEPTED = ["rgb8", "bgr8", "rgba8", "bgra8", "mono8"]
_DEFAULT_RESIZE_MODE = "stretch"
_DEFAULT_INTERP = "bilinear"
_DEFAULT_OUTPUT_DTYPE = "float32"
_DEFAULT_COLOR_HANDLING = "convert_to_rgb"


def build_canonical_preprocess(
    *,
    forge_config: dict[str, Any] | None = None,
    dataset_manifest: dict[str, Any] | None = None,
    backend: str = "scalar",
    input_variant: dict[str, Any] | None = None,
    require_image_semantics: bool | None = None,
) -> dict[str, Any]:
    """Build a canonical preprocess contract matching native ``preprocess_config_from_json``.

    For ``raw_tensor`` adapters the contract is still emitted with safe defaults when
    width/height/layout/scale/mean/std can be derived; otherwise a typed error is raised
    only when image semantics are required.
    """
    forge_config = forge_config or {}
    model_cfg = forge_config.get("model") or {}
    adapter_name = str(model_cfg.get("adapter") or "raw_tensor")
    if require_image_semantics is None:
        require_image_semantics = adapter_name in {
            "image_classification",
            "yolo_v8_detection",
        }

    layers: list[dict[str, Any]] = []
    # 1. Explicit Forge/model preprocessing configuration
    for key in ("preprocess", "preprocess_contract"):
        raw = model_cfg.get(key)
        if isinstance(raw, dict) and raw:
            layers.append(_normalize_legacy_aliases(raw))
    # 2. Dataset preprocessing contract
    if dataset_manifest is not None:
        ds = dataset_manifest.get("preprocess_contract")
        if isinstance(ds, dict) and ds:
            layers.append(_normalize_legacy_aliases(ds))
    # 3. Fixed model input shape/layout from expected_input
    expected = model_cfg.get("expected_input") or {}
    if isinstance(expected, dict) and expected:
        inferred = _infer_from_expected_input(expected)
        if inferred:
            layers.append(inferred)
    # input_variant may override layout/scale/mean/std explicitly
    if isinstance(input_variant, dict) and input_variant:
        layers.append(_normalize_legacy_aliases(input_variant))

    merged = _merge_layers(layers)
    merged["backend"] = backend if backend in {"scalar", "neon", "neon_auto"} else "scalar"
    merged.setdefault("accepted_source_formats", list(_DEFAULT_ACCEPTED))
    merged.setdefault("resize_mode", _DEFAULT_RESIZE_MODE)
    merged.setdefault("resize_interpolation", _DEFAULT_INTERP)
    merged.setdefault("output_dtype", _DEFAULT_OUTPUT_DTYPE)
    merged.setdefault("source_color_handling", _DEFAULT_COLOR_HANDLING)
    merged.setdefault("swap_rb", False)
    merged.setdefault("letterbox_pad_value", None)

    missing = _required_semantic_gaps(merged)
    if missing:
        if require_image_semantics or adapter_name != "raw_tensor":
            raise PerceptShiftError(
                code=ErrorCode.CONFIG_INVALID,
                message=(
                    "Cannot build canonical preprocess contract; missing semantic fields: "
                    + ", ".join(missing)
                ),
                remediation=(
                    "Set model.preprocess (or dataset preprocess_contract) with "
                    "input_width/input_height/input_layout/scale/mean/std. "
                    "Do not rely on invented ImageNet defaults for arbitrary models."
                ),
                details={"missing_fields": missing, "adapter": adapter_name},
            )
        # raw_tensor path: provide a minimal placeholder only when dimensions are known
        # from expected_input; otherwise leave a tensor-only placeholder that native
        # rejects for image paths but is unused for TensorBytes.
        if "input_width" not in merged or "input_height" not in merged:
            # Safe tensor-only placeholder — native image path will refuse width==0.
            merged.setdefault("input_width", 1)
            merged.setdefault("input_height", 1)
            merged.setdefault("input_layout", "nchw")
            merged.setdefault("scale", 1.0 / 255.0)
            merged.setdefault("mean", [0.0, 0.0, 0.0])
            merged.setdefault("std", [1.0, 1.0, 1.0])
        else:
            for field, default in (
                ("input_layout", "nchw"),
                ("scale", 1.0 / 255.0),
                ("mean", [0.0, 0.0, 0.0]),
                ("std", [1.0, 1.0, 1.0]),
            ):
                merged.setdefault(field, default)

    contract = {
        "input_width": int(merged["input_width"]),
        "input_height": int(merged["input_height"]),
        "input_layout": str(merged["input_layout"]),
        "accepted_source_formats": list(merged["accepted_source_formats"]),
        "source_color_handling": str(merged["source_color_handling"]),
        "resize_mode": str(merged["resize_mode"]),
        "resize_interpolation": str(merged["resize_interpolation"]),
        "scale": float(merged["scale"]),
        "mean": [float(x) for x in merged["mean"]],
        "std": [float(x) for x in merged["std"]],
        "swap_rb": bool(merged["swap_rb"]),
        "letterbox_pad_value": merged.get("letterbox_pad_value"),
        "output_dtype": str(merged["output_dtype"]),
        "backend": str(merged["backend"]),
    }
    validate_document(contract, "preprocess_contract")
    return contract


def _normalize_legacy_aliases(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert obsolete template fields into canonical names without inventing values."""
    out: dict[str, Any] = dict(raw)
    if "input_width" not in out and "width" in out:
        out["input_width"] = out["width"]
    if "input_height" not in out and "height" in out:
        out["input_height"] = out["height"]
    if "input_layout" not in out and "layout" in out:
        out["input_layout"] = out["layout"]
    if "output_dtype" not in out and "dtype" in out:
        out["output_dtype"] = out["dtype"]
    # resize: [w,h] or [h,w] — treat as width,height when both dims present
    resize = out.get("resize")
    if isinstance(resize, list) and len(resize) == 2:
        out.setdefault("input_width", int(resize[0]))
        out.setdefault("input_height", int(resize[1]))
    # Obsolete color_order → swap_rb only when unambiguous
    color_order = out.get("color_order")
    if isinstance(color_order, str) and "swap_rb" not in out:
        if color_order.lower() == "bgr":
            out["swap_rb"] = True
        elif color_order.lower() == "rgb":
            out["swap_rb"] = False
    return out


def _infer_from_expected_input(expected: dict[str, Any]) -> dict[str, Any]:
    inferred: dict[str, Any] = {}
    shape = expected.get("shape") or expected.get("input_shape")
    layout = expected.get("layout") or expected.get("input_layout")
    if isinstance(shape, list) and len(shape) >= 4:
        dims = [int(d) if isinstance(d, int) and d > 0 else None for d in shape]
        # Prefer explicit layout; otherwise infer NCHW when channel dim is 3 at index 1
        if layout in {"nchw", "nhwc"}:
            inferred["input_layout"] = layout
        elif dims[1] == 3:
            inferred["input_layout"] = "nchw"
        elif dims[-1] == 3:
            inferred["input_layout"] = "nhwc"
        layout_eff = inferred.get("input_layout")
        if layout_eff == "nchw" and dims[-2] and dims[-1]:
            inferred["input_height"] = dims[-2]
            inferred["input_width"] = dims[-1]
        elif layout_eff == "nhwc" and dims[1] and dims[2]:
            inferred["input_height"] = dims[1]
            inferred["input_width"] = dims[2]
    if "input_layout" in expected and "input_layout" not in inferred:
        inferred["input_layout"] = expected["input_layout"]
    for key in ("scale", "mean", "std", "swap_rb"):
        if key in expected:
            inferred[key] = expected[key]
    return inferred


_LEGACY_KEYS = frozenset(
    {
        "width",
        "height",
        "layout",
        "dtype",
        "color_order",
        "resize",
        "expected_input",
        "input_variant",
    }
)


def _merge_layers(layers: list[dict[str, Any]]) -> dict[str, Any]:
    """Earlier layers win (higher precedence); later layers only fill gaps."""
    result: dict[str, Any] = {}
    for layer in layers:
        for key, value in layer.items():
            if key in _LEGACY_KEYS or value is None:
                continue
            if key not in result:
                result[key] = value
    return result


def _required_semantic_gaps(merged: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("input_width", "input_height", "input_layout", "scale", "mean", "std"):
        if key not in merged or merged[key] is None:
            missing.append(key)
            continue
        if key in {"mean", "std"}:
            val = merged[key]
            if not isinstance(val, (list, tuple)) or len(val) != 3:
                missing.append(key)
        if key in {"input_width", "input_height"}:
            try:
                if int(merged[key]) <= 0:
                    missing.append(key)
            except (TypeError, ValueError):
                missing.append(key)
        if key == "input_layout" and merged[key] not in {"nchw", "nhwc"}:
            missing.append(key)
    return missing
