"""DB-facing metrics service: load tenant-scoped events for an agent over a
window and turn them into scorecards / trends."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent, MonitoredAgent
from app.metrics.compute import (
    EventRow,
    ScorecardData,
    compute_daily_trend,
    compute_scorecard,
)
from app.schemas import Scorecard, TrendPoint


def _load_events(
    db: Session, *, tenant_id: str, agent_id: str, since: datetime
) -> list[EventRow]:
    rows = db.scalars(
        select(AgentEvent).where(
            AgentEvent.tenant_id == tenant_id,      # tenant isolation
            AgentEvent.agent_id == agent_id,
            AgentEvent.occurred_at >= since,
        )
    ).all()
    return [
        EventRow(
            occurred_at_date=r.occurred_at.date().isoformat(),
            latency_ms=r.latency_ms, cost_usd=r.cost_usd,
            quality_score=r.quality_score, human_override=r.human_override, error=r.error,
        )
        for r in rows
    ]


def scorecard_for_agent(
    db: Session, *, tenant_id: str, agent: MonitoredAgent, window_days: int
) -> Scorecard:
    since = datetime.now(UTC) - timedelta(days=window_days)
    sc: ScorecardData = compute_scorecard(
        _load_events(db, tenant_id=tenant_id, agent_id=agent.id, since=since)
    )
    return Scorecard(
        agent_id=agent.id, agent_name=agent.name, window_days=window_days,
        queries=sc.queries, total_cost_usd=sc.total_cost_usd,
        cost_per_query_usd=sc.cost_per_query_usd,
        latency_p50_ms=sc.latency_p50_ms, latency_p95_ms=sc.latency_p95_ms,
        latency_p99_ms=sc.latency_p99_ms, avg_quality_score=sc.avg_quality_score,
        human_override_rate=sc.human_override_rate,
        human_override_count=sc.human_override_count, error_rate=sc.error_rate,
        slo_latency_ok=sc.latency_p99_ms <= agent.slo_p99_latency_ms,
        override_ok=sc.human_override_rate <= agent.max_override_rate,
        quality_ok=(
            sc.avg_quality_score is None or sc.avg_quality_score >= agent.min_quality_score
        ),
    )


def trend_for_agent(
    db: Session, *, tenant_id: str, agent_id: str, days: int
) -> list[TrendPoint]:
    since = datetime.now(UTC) - timedelta(days=days)
    events = _load_events(db, tenant_id=tenant_id, agent_id=agent_id, since=since)
    return [TrendPoint(**pt) for pt in compute_daily_trend(events)]
