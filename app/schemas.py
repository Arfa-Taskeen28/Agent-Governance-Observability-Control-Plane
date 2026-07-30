"""Pydantic schemas for the control plane: agent registration, telemetry
ingestion, scorecards, trends, alerts, and compliance reports."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    kind: str = Field(..., min_length=1, max_length=64)
    risk_category: str = Field(default="limited", pattern="^(minimal|limited|high|unacceptable)$")
    base_url: str | None = Field(default=None, max_length=512)
    slo_p99_latency_ms: int = Field(default=3000, gt=0)
    max_override_rate: float = Field(default=0.25, ge=0, le=1)
    min_quality_score: float = Field(default=0.70, ge=0, le=1)


class AgentOut(BaseModel):
    id: str
    name: str
    kind: str
    risk_category: str
    slo_p99_latency_ms: int
    max_override_rate: float
    min_quality_score: float


class EventIn(BaseModel):
    """One telemetry event emitted by a monitored agent."""

    event_type: str = Field(default="query", max_length=64)
    latency_ms: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    tokens: int = Field(default=0, ge=0)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    decided_by: str = Field(default="llm", max_length=16)
    human_override: bool = False
    error: bool = False
    trace_id: str | None = Field(default=None, max_length=64)
    occurred_at: str | None = None  # ISO8601; defaults to now if omitted


class Scorecard(BaseModel):
    agent_id: str
    agent_name: str
    window_days: int
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
    # SLO health (True = within threshold).
    slo_latency_ok: bool
    override_ok: bool
    quality_ok: bool


class TrendPoint(BaseModel):
    date: str            # YYYY-MM-DD
    queries: int
    cost_per_query_usd: float
    latency_p99_ms: float
    avg_quality_score: float | None
    human_override_rate: float


class AlertOut(BaseModel):
    id: str
    agent_id: str
    kind: str
    severity: str
    message: str
    metric_value: float
    threshold: float
    notified: bool
    created_at: str
