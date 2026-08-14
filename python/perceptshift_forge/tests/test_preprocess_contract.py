"""Preprocess contract builder tests."""

from __future__ import annotations

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_forge.preprocess import build_canonical_preprocess


def test_image_adapter_fails_without_semantics() -> None:
    try:
        build_canonical_preprocess(forge_config={"model": {"adapter": "yolo_v8_detection"}})
        raise AssertionError("expected CONFIG_INVALID")
    except PerceptShiftError as exc:
        assert exc.code == ErrorCode.CONFIG_INVALID
        assert "mean" in str(exc.details.get("missing_fields") or exc.message)


def test_forge_preprocess_wins_over_dataset() -> None:
    contract = build_canonical_preprocess(
        forge_config={
            "model": {
                "adapter": "image_classification",
                "preprocess": {
                    "input_width": 16,
                    "input_height": 16,
                    "input_layout": "nchw",
                    "scale": 0.5,
                    "mean": [0.1, 0.2, 0.3],
                    "std": [1.0, 1.0, 1.0],
                    "accepted_source_formats": ["rgb8"],
                    "resize_mode": "stretch",
                    "resize_interpolation": "bilinear",
                    "swap_rb": False,
                    "output_dtype": "float32",
                    "backend": "scalar",
                },
            }
        },
        dataset_manifest={
            "preprocess_contract": {
                "input_width": 8,
                "input_height": 8,
                "input_layout": "nhwc",
                "scale": 1.0,
                "mean": [0.0, 0.0, 0.0],
                "std": [1.0, 1.0, 1.0],
            }
        },
        backend="neon_auto",
    )
    assert contract["input_width"] == 16
    assert contract["input_layout"] == "nchw"
    assert contract["scale"] == 0.5
    assert contract["backend"] == "neon_auto"


def test_legacy_aliases_converted() -> None:
    contract = build_canonical_preprocess(
        forge_config={
            "model": {
                "adapter": "image_classification",
                "preprocess_contract": {
                    "width": 10,
                    "height": 12,
                    "layout": "nchw",
                    "dtype": "float32",
                    "color_order": "rgb",
                    "scale": 1.0 / 255.0,
                    "mean": [0.0, 0.0, 0.0],
                    "std": [1.0, 1.0, 1.0],
                },
            }
        },
    )
    assert contract["input_width"] == 10
    assert contract["input_height"] == 12
    assert contract["swap_rb"] is False
