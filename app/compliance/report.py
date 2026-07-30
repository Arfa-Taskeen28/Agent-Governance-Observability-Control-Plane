"""Compliance report generator — the single most enterprise-recognizable
artifact in the portfolio.

Produces a structured, non-technical-stakeholder-readable markdown report for one
agent: EU AI Act risk classification, reporting period, volume & cost, quality,
human-oversight statistics, an explainability note, and the alert history. This
is what a governance/risk officer would attach to an audit file.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, MonitoredAgent
from app.metrics.service import scorecard_for_agent

_RISK_NOTE = {
    "high": "High-risk (EU AI Act Annex III). Subject to human-oversight, "
            "record-keeping, transparency, and accuracy obligations.",
    "limited": "Limited-risk. Transparency obligations apply (users are informed "
               "they interact with an AI system).",
    "minimal": "Minimal-risk. No mandatory obligations; monitored voluntarily.",
    "unacceptable": "Unacceptable-risk. Prohibited use — must not be deployed.",
}


def generate_markdown_report(
    db: Session, *, tenant_id: str, agent: MonitoredAgent, window_days: int = 30
) -> str:
    sc = scorecard_for_agent(db, tenant_id=tenant_id, agent=agent, window_days=window_days)
    since = datetime.now(UTC) - timedelta(days=window_days)
    now = datetime.now(UTC)

    alerts = db.scalars(
        select(Alert).where(
            Alert.tenant_id == tenant_id, Alert.agent_id == agent.id,
            Alert.created_at >= since,
        ).order_by(Alert.created_at.desc())
    ).all()

    quality = "n/a" if sc.avg_quality_score is None else f"{sc.avg_quality_score:.2f}"
    ok = lambda b: "✅ within threshold" if b else "⚠️ BREACH"  # noqa: E731

    lines = [
        f"# AI Agent Compliance Report — {agent.name}",
        "",
        f"*Generated {now.date().isoformat()} · reporting period "
        f"{since.date().isoformat()} → {now.date().isoformat()} ({window_days} days)*",
        "",
        "## 1. System classification",
        f"- **Agent:** {agent.name} (`{agent.kind}`)",
        f"- **EU AI Act risk category:** **{agent.risk_category}**",
        f"- {_RISK_NOTE.get(agent.risk_category, 'Risk category not mapped.')}",
        "",
        "## 2. Operational summary",
        f"- **Queries processed:** {sc.queries}",
        f"- **Total cost:** ${sc.total_cost_usd:.4f}  ·  "
        f"**cost/query:** ${sc.cost_per_query_usd:.5f}",
        f"- **Latency:** p50 {sc.latency_p50_ms:.0f}ms · p95 {sc.latency_p95_ms:.0f}ms · "
        f"p99 {sc.latency_p99_ms:.0f}ms (SLO {agent.slo_p99_latency_ms}ms — "
        f"{ok(sc.slo_latency_ok)})",
        f"- **Error rate:** {sc.error_rate:.1%}",
        "",
        "## 3. Quality & evaluation",
        f"- **Average quality score:** {quality} "
        f"(floor {agent.min_quality_score:.2f} — {ok(sc.quality_ok)})",
        "- Scores are produced by an automated evaluation suite (DeepEval/RAGAS-style), "
        "not self-reported by the agent.",
        "",
        "## 4. Human oversight",
        f"- **Human-override rate:** {sc.human_override_rate:.1%} "
        f"(max {agent.max_override_rate:.0%} — {ok(sc.override_ok)})",
        f"- Of {sc.queries} decisions, {sc.human_override_count} "
        f"were overridden by a human reviewer.",
        "- A human-in-the-loop checkpoint governs high-impact actions for this agent class.",
        "",
        "## 5. Explainability",
        "- Every decision is written to an immutable, per-decision audit trail in the source "
        "system, attributing each step to code / trained model / LLM / human.",
        "- The full reasoning chain for any single decision is reconstructable on demand — "
        "the evidence basis for Art. 13 transparency.",
        "",
        "## 6. Alerts in period",
    ]
    if alerts:
        for a in alerts:
            lines.append(
                f"- [{a.severity.value.upper()}] {a.created_at.date().isoformat()} — "
                f"{a.message}"
            )
    else:
        lines.append("- No threshold breaches recorded in the reporting period.")

    lines += [
        "",
        "---",
        "*This report is generated automatically by the Agent Governance & "
        "Observability Control Plane. It documents operational and oversight "
        "controls; it is not a legal conformity assessment.*",
    ]
    return "\n".join(lines)
