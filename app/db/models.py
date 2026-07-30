"""Multi-tenant data model for the agent governance & observability control plane.

The control plane is itself multi-tenant (one tenant = one organisation operating
a fleet of agents). Each :class:`MonitoredAgent` emits :class:`AgentEvent`
telemetry (one row per query/decision) that the plane aggregates into scorecards.
Threshold breaches become :class:`Alert` rows.
"""
from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MonitoredAgent(Base):
    """One agent under governance (e.g. the support / SDR / doc-intel / claims
    agents). Carries its EU AI Act risk category and its SLO thresholds."""

    __tablename__ = "monitored_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)  # support|sdr|docintel|claims|...
    risk_category: Mapped[str] = mapped_column(String(32), default="limited", nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # for liveness poll

    # SLO / governance thresholds (breach -> alert).
    slo_p99_latency_ms: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    max_override_rate: Mapped[float] = mapped_column(Float, default=0.25, nullable=False)
    min_quality_score: Mapped[float] = mapped_column(Float, default=0.70, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_agents_tenant", "tenant_id"),)


class AgentEvent(Base):
    """One unit of agent telemetry: a single query/decision. This is the raw
    material every scorecard is aggregated from."""

    __tablename__ = "agent_events"

    # Monotonic id so time-ordered reads are stable even at identical timestamps.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("monitored_agents.id"), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    event_type: Mapped[str] = mapped_column(String(64), default="query", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Quality/eval score in [0,1] (DeepEval/RAGAS-style), nullable if not scored.
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(16), default="llm", nullable=False)
    human_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # link to source audit
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_events_tenant_agent_time", "tenant_id", "agent_id", "occurred_at"),
    )


class AlertSeverity(str, enum.Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class Alert(Base):
    """A threshold breach on an agent's SLO / governance metric."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("monitored_agents.id"), nullable=False)
    # kind: latency_p99 | override_rate | quality
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # slack sent?
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_alerts_tenant_created", "tenant_id", "created_at"),)
