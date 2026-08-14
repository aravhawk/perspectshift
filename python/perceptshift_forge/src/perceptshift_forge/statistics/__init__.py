"""Benchmark statistics: percentiles, MAD, bootstrap CI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from perceptshift_common.errors import ErrorCode, PerceptShiftError


@dataclass(slots=True)
class SummaryStats:
    count: int
    minimum: float
    maximum: float
    mean: float
    std: float
    p50: float
    p90: float
    p95: float
    p99: float
    mad: float
    coefficient_of_variation: float | None
    bootstrap_ci: dict[str, dict[str, float]] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "std": self.std,
            "p50": self.p50,
            "p90": self.p90,
            "p95": self.p95,
            "p99": self.p99,
            "mad": self.mad,
            "coefficient_of_variation": self.coefficient_of_variation,
            "bootstrap_ci": self.bootstrap_ci,
        }


def _percentile(sorted_values: np.ndarray, q: float) -> float:
    """Linear interpolation percentile (numpy default method)."""
    return float(np.percentile(sorted_values, q, method="linear"))


def median_absolute_deviation(values: np.ndarray) -> float:
    median = float(np.median(values))
    return float(np.median(np.abs(values - median)))


def bootstrap_confidence_interval(
    values: np.ndarray,
    *,
    statistic: str,
    resamples: int,
    confidence_level: float,
    seed: int,
) -> dict[str, float]:
    if resamples < 1:
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message="bootstrap resamples must be >= 1",
        )
    rng = np.random.default_rng(seed)
    n = values.size
    stats = np.empty(resamples, dtype=np.float64)
    for i in range(resamples):
        sample = values[rng.integers(0, n, size=n)]
        if statistic == "mean":
            stats[i] = float(np.mean(sample))
        elif statistic == "p99":
            stats[i] = _percentile(np.sort(sample), 99)
        elif statistic == "p50":
            stats[i] = _percentile(np.sort(sample), 50)
        else:
            raise PerceptShiftError(
                code=ErrorCode.CONFIG_INVALID,
                message=f"Unsupported bootstrap statistic: {statistic}",
            )
    alpha = 1.0 - confidence_level
    lower = float(np.quantile(stats, alpha / 2.0))
    upper = float(np.quantile(stats, 1.0 - alpha / 2.0))
    return {
        "statistic": float(np.mean(stats)),
        "lower": lower,
        "upper": upper,
        "confidence_level": confidence_level,
        "resamples": float(resamples),
    }


def summarize_latencies(
    samples_ns: list[int] | list[float] | np.ndarray,
    *,
    bootstrap_resamples: int = 0,
    confidence_level: float = 0.95,
    seed: int = 1729,
    bootstrap_statistics: tuple[str, ...] = ("mean", "p99"),
) -> SummaryStats:
    values = np.asarray(samples_ns, dtype=np.float64)
    if values.size == 0:
        raise PerceptShiftError(
            code=ErrorCode.INTERNAL_INVARIANT_FAILED,
            message="Cannot summarize empty sample set",
        )
    if not np.isfinite(values).all():
        raise PerceptShiftError(
            code=ErrorCode.INTERNAL_INVARIANT_FAILED,
            message="Latency samples must be finite",
        )
    sorted_values = np.sort(values)
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    cov = (std / mean) if mean != 0.0 else None
    bootstrap_ci: dict[str, dict[str, float]] | None = None
    if bootstrap_resamples > 0:
        bootstrap_ci = {
            name: bootstrap_confidence_interval(
                values,
                statistic=name,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
                seed=seed + idx,
            )
            for idx, name in enumerate(bootstrap_statistics)
        }
    return SummaryStats(
        count=int(values.size),
        minimum=float(sorted_values[0]),
        maximum=float(sorted_values[-1]),
        mean=mean,
        std=std,
        p50=_percentile(sorted_values, 50),
        p90=_percentile(sorted_values, 90),
        p95=_percentile(sorted_values, 95),
        p99=_percentile(sorted_values, 99),
        mad=median_absolute_deviation(values),
        coefficient_of_variation=cov,
        bootstrap_ci=bootstrap_ci,
    )
