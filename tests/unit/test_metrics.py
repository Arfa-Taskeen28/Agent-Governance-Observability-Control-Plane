"""The metric math the whole dashboard depends on: percentiles, scorecard
aggregation, and daily trend bucketing."""
from __future__ import annotations

from app.metrics.compute import (
    EventRow,
    compute_daily_trend,
    compute_scorecard,
    percentile,
)


def test_percentile_matches_numpy_linear_method():
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile(data, 50) == 5.5    # median of 1..10
    assert percentile(data, 0) == 1.0
    assert percentile(data, 100) == 10.0
    # p90 by linear interpolation: rank = 0.9*9 = 8.1 -> 9 + 0.1*(10-9) = 9.1
    assert round(percentile(data, 90), 2) == 9.1


def test_percentile_edge_cases():
    assert percentile([], 99) == 0.0
    assert percentile([42], 99) == 42.0


def _ev(latency, cost=0.01, quality=0.9, override=False, error=False, day="2026-07-01"):
    return EventRow(occurred_at_date=day, latency_ms=latency, cost_usd=cost,
                    quality_score=quality, human_override=override, error=error)


def test_scorecard_aggregation():
    events = [_ev(100), _ev(200), _ev(300, override=True), _ev(400, error=True)]
    sc = compute_scorecard(events)
    assert sc.queries == 4
    assert round(sc.total_cost_usd, 2) == 0.04
    assert round(sc.cost_per_query_usd, 3) == 0.01
    assert sc.human_override_rate == 0.25   # 1 of 4
    assert sc.human_override_count == 1     # exact count, not back-computed
    assert sc.error_rate == 0.25            # 1 of 4
    assert sc.avg_quality_score == 0.9
    assert sc.latency_p50_ms == 250.0       # median of 100,200,300,400


def test_scorecard_empty_is_safe():
    sc = compute_scorecard([])
    assert sc.queries == 0
    assert sc.cost_per_query_usd == 0.0
    assert sc.avg_quality_score is None
    assert sc.human_override_rate == 0.0


def test_quality_ignores_missing_scores():
    events = [_ev(100, quality=0.8), _ev(100, quality=None), _ev(100, quality=1.0)]
    sc = compute_scorecard(events)
    assert sc.avg_quality_score == 0.9  # mean of 0.8 and 1.0 only


def test_daily_trend_buckets_by_day():
    events = [_ev(100, day="2026-07-01"), _ev(300, day="2026-07-01"),
              _ev(200, day="2026-07-02")]
    trend = compute_daily_trend(events)
    assert [p["date"] for p in trend] == ["2026-07-01", "2026-07-02"]
    assert trend[0]["queries"] == 2
    assert trend[1]["queries"] == 1
