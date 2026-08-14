"""Shared evaluation result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EvaluationResult:
    metric_name: str
    metric_direction: str
    value: float
    sample_count: int
    class_breakdown: dict[str, Any]
    attestation: dict[str, Any]
    unavailable_reason: str | None = None
