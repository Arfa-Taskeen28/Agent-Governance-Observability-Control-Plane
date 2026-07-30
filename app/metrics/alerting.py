"""Threshold-breach alerting.

Evaluates an agent's current scorecard against its SLO / governance thresholds
and records :class:`Alert` rows for any breach (deduplicated against recent open
alerts). If a Slack webhook is configured, the alert is POSTed best-effort.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, AlertSeverity, MonitoredAgent
from app.metrics.service import scorecard_for_agent
from app.observability.logging import get_logger

log = get_logger("alerting")

# Don't re-fire the same breach within this window.
_DEDUP_WINDOW = timedelta(hours=1)


def evaluate_agent(
    db: Session, *, tenant_id: str, agent: MonitoredAgent, window_days: int,
    slack_webhook_url: str = "",
) -> list[Alert]:
    sc = scorecard_for_agent(db, tenant_id=tenant_id, agent=agent, window_days=window_days)
    breaches: list[tuple[str, AlertSeverity, str, float, float]] = []

    if sc.queries > 0 and sc.latency_p99_ms > agent.slo_p99_latency_ms:
        breaches.append((
            "latency_p99", AlertSeverity.CRITICAL,
            f"p99 latency {sc.latency_p99_ms}ms exceeds SLO {agent.slo_p99_latency_ms}ms",
            sc.latency_p99_ms, float(agent.slo_p99_latency_ms),
        ))
    if sc.queries > 0 and sc.human_override_rate > agent.max_override_rate:
        breaches.append((
            "override_rate", AlertSeverity.WARNING,
            f"human-override rate {sc.human_override_rate:.0%} exceeds "
            f"{agent.max_override_rate:.0%}",
            sc.human_override_rate, agent.max_override_rate,
        ))
    if sc.avg_quality_score is not None and sc.avg_quality_score < agent.min_quality_score:
        breaches.append((
            "quality", AlertSeverity.WARNING,
            f"avg quality {sc.avg_quality_score:.2f} below floor {agent.min_quality_score:.2f}",
            sc.avg_quality_score, agent.min_quality_score,
        ))

    created: list[Alert] = []
    for kind, severity, message, value, threshold in breaches:
        if _recently_alerted(db, tenant_id=tenant_id, agent_id=agent.id, kind=kind):
            continue
        alert = Alert(
            tenant_id=tenant_id, agent_id=agent.id, kind=kind, severity=severity,
            message=message, metric_value=round(value, 4), threshold=round(threshold, 4),
        )
        db.add(alert)
        db.flush()
        if slack_webhook_url and _notify_slack(slack_webhook_url, agent, alert):
            alert.notified = True
        created.append(alert)

    db.commit()
    return created


def _recently_alerted(db: Session, *, tenant_id: str, agent_id: str, kind: str) -> bool:
    since = datetime.now(UTC) - _DEDUP_WINDOW
    existing = db.scalar(
        select(Alert).where(
            Alert.tenant_id == tenant_id, Alert.agent_id == agent_id,
            Alert.kind == kind, Alert.created_at >= since,
        ).limit(1)
    )
    return existing is not None


def _notify_slack(webhook_url: str, agent: MonitoredAgent, alert: Alert) -> bool:
    payload = json.dumps({
        "text": f":rotating_light: *{agent.name}* [{alert.severity.value}] {alert.message}"
    }).encode()
    try:
        req = urllib.request.Request(
            webhook_url, data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=4)  # noqa: S310 - operator-configured webhook
        return True
    except Exception as exc:  # noqa: BLE001 - alerting must never break the request
        log.warning("alert.slack_failed", agent=agent.name, error=str(exc))
        return False
