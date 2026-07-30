"""Metric aggregation — the heart of the control plane.

Pure-Python (no numpy) so it's dependency-light and every number is testable.
Computes per-agent scorecards (cost/query, latency percentiles, quality,
human-override rate) and daily trends over a window.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class EventRow:
    occurred_at_date: str  # YYYY-MM-DD
    latency_ms: int
    cost_usd: float
    quality_score: float | None
    human_override: bool
    error: bool


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile (same method as numpy's default).

    ``p`` in [0,100]. Empty -> 0.0. This is the one piece of math the whole
    dashboard's latency SLOs depend on, so it's kept explicit and tested.
    """
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = (p / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


@dataclass
class ScorecardData:
    queries: int
    total_cost_usd: float
    cost_per_query_usd: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    avg_quality_score: float | None
    human_override_rate: float
    human_override_count: int
    error_rate: float


def compute_scorecard(events: list[EventRow]) -> ScorecardData:
    n = len(events)
    if n == 0:
        return ScorecardData(0, 0.0, 0.0, 0.0, 0.0, 0.0, None, 0.0, 0, 0.0)

    latencies = [float(e.latency_ms) for e in events]
    total_cost = sum(e.cost_usd for e in events)
    overrides = sum(1 for e in events if e.human_override)
    errors = sum(1 for e in events if e.error)
    quals = [e.quality_score for e in events if e.quality_score is not None]

    return ScorecardData(
        queries=n,
        total_cost_usd=round(total_cost, 6),
        cost_per_query_usd=round(total_cost / n, 6),
        latency_p50_ms=round(percentile(latencies, 50), 2),
        latency_p95_ms=round(percentile(latencies, 95), 2),
        latency_p99_ms=round(percentile(latencies, 99), 2),
        avg_quality_score=round(sum(quals) / len(quals), 4) if quals else None,
        human_override_rate=round(overrides / n, 4),
        human_override_count=overrides,   # exact count, not back-computed from the rate
        error_rate=round(errors / n, 4),
    )


def compute_daily_trend(events: list[EventRow]) -> list[dict]:
    """Bucket events by day and compute a mini-scorecard per day (for drift)."""
    by_day: dict[str, list[EventRow]] = defaultdict(list)
    for e in events:
        by_day[e.occurred_at_date].append(e)

    out: list[dict] = []
    for day in sorted(by_day):
        sc = compute_scorecard(by_day[day])
        out.append({
            "date": day,
            "queries": sc.queries,
            "cost_per_query_usd": sc.cost_per_query_usd,
            "latency_p99_ms": sc.latency_p99_ms,
            "avg_quality_score": sc.avg_quality_score,
            "human_override_rate": sc.human_override_rate,
        })
    return out
