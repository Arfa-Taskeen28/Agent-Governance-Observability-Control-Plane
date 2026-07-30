"""Monitored-agent registration + telemetry ingestion + scorecards/trends."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tenant import TenantContext, get_tenant_context
from app.config import get_settings
from app.db.base import get_db
from app.db.models import AgentEvent, MonitoredAgent
from app.metrics.alerting import evaluate_agent
from app.metrics.service import scorecard_for_agent, trend_for_agent
from app.schemas import AgentIn, AgentOut, EventIn, Scorecard, TrendPoint

router = APIRouter(prefix="/agents", tags=["agents"])


def _get_agent(db: Session, tenant_id: str, agent_id: str) -> MonitoredAgent:
    agent = db.get(MonitoredAgent, agent_id)
    if agent is None or agent.tenant_id != tenant_id:  # tenant isolation
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def to_agent_out(a: MonitoredAgent) -> AgentOut:
    return AgentOut(
        id=a.id, name=a.name, kind=a.kind, risk_category=a.risk_category,
        slo_p99_latency_ms=a.slo_p99_latency_ms, max_override_rate=a.max_override_rate,
        min_quality_score=a.min_quality_score,
    )


@router.post("", response_model=AgentOut)
def register_agent(
    body: AgentIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> AgentOut:
    agent = MonitoredAgent(tenant_id=ctx.tenant_id, **body.model_dump())
    db.add(agent)
    db.commit()
    return to_agent_out(agent)


@router.get("", response_model=list[AgentOut])
def list_agents(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[AgentOut]:
    rows = db.scalars(
        select(MonitoredAgent).where(MonitoredAgent.tenant_id == ctx.tenant_id)
        .order_by(MonitoredAgent.created_at.asc())
    ).all()
    return [to_agent_out(a) for a in rows]


@router.post("/{agent_id}/events")
def ingest_event(
    agent_id: str,
    body: EventIn,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    agent = _get_agent(db, ctx.tenant_id, agent_id)
    occurred = _parse_ts(body.occurred_at)
    ev = AgentEvent(
        tenant_id=ctx.tenant_id, agent_id=agent.id, occurred_at=occurred,
        event_type=body.event_type, latency_ms=body.latency_ms, cost_usd=body.cost_usd,
        tokens=body.tokens, quality_score=body.quality_score, decided_by=body.decided_by,
        human_override=body.human_override, error=body.error, trace_id=body.trace_id,
    )
    db.add(ev)
    db.commit()
    return {"ingested": 1, "agent_id": agent.id}


@router.post("/{agent_id}/events/batch")
def ingest_events_batch(
    agent_id: str,
    events: list[EventIn],
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    agent = _get_agent(db, ctx.tenant_id, agent_id)
    for body in events:
        db.add(AgentEvent(
            tenant_id=ctx.tenant_id, agent_id=agent.id, occurred_at=_parse_ts(body.occurred_at),
            event_type=body.event_type, latency_ms=body.latency_ms, cost_usd=body.cost_usd,
            tokens=body.tokens, quality_score=body.quality_score, decided_by=body.decided_by,
            human_override=body.human_override, error=body.error, trace_id=body.trace_id,
        ))
    db.commit()
    return {"ingested": len(events), "agent_id": agent.id}


@router.get("/{agent_id}/scorecard", response_model=Scorecard)
def get_scorecard(
    agent_id: str,
    window_days: int = 7,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Scorecard:
    agent = _get_agent(db, ctx.tenant_id, agent_id)
    return scorecard_for_agent(db, tenant_id=ctx.tenant_id, agent=agent, window_days=window_days)


@router.get("/{agent_id}/trend", response_model=list[TrendPoint])
def get_trend(
    agent_id: str,
    days: int = 14,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[TrendPoint]:
    agent = _get_agent(db, ctx.tenant_id, agent_id)
    return trend_for_agent(db, tenant_id=ctx.tenant_id, agent_id=agent.id, days=days)


@router.post("/{agent_id}/evaluate")
def evaluate_thresholds(
    agent_id: str,
    window_days: int = 7,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    """Evaluate SLO/governance thresholds now; create + optionally Slack-notify
    alerts for any breach."""
    agent = _get_agent(db, ctx.tenant_id, agent_id)
    created = evaluate_agent(
        db, tenant_id=ctx.tenant_id, agent=agent, window_days=window_days,
        slack_webhook_url=get_settings().slack_webhook_url,
    )
    return {"alerts_created": len(created), "kinds": [a.kind for a in created]}


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        # Normalize to UTC so SQLite (which drops tz) and Postgres agree, and so
        # windowing/day-bucketing use one consistent clock.
        return dt.astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)
