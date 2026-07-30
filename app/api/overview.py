"""Fleet overview, alerts list, and compliance-report export."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.agents import _get_agent
from app.auth.tenant import TenantContext, get_tenant_context
from app.compliance.report import generate_markdown_report
from app.db.base import get_db
from app.db.models import Alert, MonitoredAgent
from app.metrics.service import scorecard_for_agent
from app.schemas import AlertOut

router = APIRouter(tags=["overview"])


@router.get("/overview")
def fleet_overview(
    window_days: int = 7,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> dict:
    """One call that powers the dashboard: a scorecard per monitored agent plus
    fleet-level rollups."""
    agents = db.scalars(
        select(MonitoredAgent).where(MonitoredAgent.tenant_id == ctx.tenant_id)
        .order_by(MonitoredAgent.created_at.asc())
    ).all()

    cards = [
        scorecard_for_agent(db, tenant_id=ctx.tenant_id, agent=a, window_days=window_days)
        for a in agents
    ]
    total_queries = sum(c.queries for c in cards)
    total_cost = sum(c.total_cost_usd for c in cards)
    breaching = sum(
        1 for c in cards if not (c.slo_latency_ok and c.override_ok and c.quality_ok)
    )
    # "has_alerts" reflects CURRENT health: only alerts within the same window
    # (alerts are never deleted, so an all-time check would never clear).
    since = datetime.now(UTC) - timedelta(days=window_days)
    recent_alert = db.scalar(
        select(Alert).where(
            Alert.tenant_id == ctx.tenant_id, Alert.created_at >= since
        ).limit(1)
    )

    return {
        "window_days": window_days,
        "agent_count": len(agents),
        "total_queries": total_queries,
        "total_cost_usd": round(total_cost, 4),
        "agents_breaching_slo": breaching,
        "has_alerts": recent_alert is not None,
        "scorecards": [
            {**c.model_dump(), "risk_category": a.risk_category, "kind": a.kind}
            for a, c in zip(agents, cards, strict=True)
        ],
    }


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    rows = db.scalars(
        select(Alert).where(Alert.tenant_id == ctx.tenant_id)
        .order_by(Alert.created_at.desc()).limit(100)
    ).all()
    return [
        AlertOut(
            id=a.id, agent_id=a.agent_id, kind=a.kind, severity=a.severity.value,
            message=a.message, metric_value=a.metric_value, threshold=a.threshold,
            notified=a.notified, created_at=a.created_at.isoformat(),
        )
        for a in rows
    ]


@router.get("/agents/{agent_id}/compliance-report")
def compliance_report(
    agent_id: str,
    window_days: int = 30,
    download: bool = False,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    agent = _get_agent(db, ctx.tenant_id, agent_id)
    md = generate_markdown_report(db, tenant_id=ctx.tenant_id, agent=agent, window_days=window_days)
    if download:
        filename = f"compliance-{agent.kind}-{agent.id[:8]}.md"
        return Response(
            content=md, media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return {"agent_id": agent.id, "markdown": md}
