"""End-to-end through the API: register agent -> ingest events -> scorecard ->
threshold alerts -> compliance report. Plus tenant isolation."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app


def _signup(client: TestClient) -> dict:
    r = client.post("/tenants/signup", json={"name": f"org-{uuid.uuid4()}"}).json()
    return {"Authorization": f"Bearer {r['access_token']}"}


def _register(client, auth, **kw):
    body = {"name": "Support Agent", "kind": "support", "risk_category": "limited",
            "slo_p99_latency_ms": 2000, "max_override_rate": 0.20, "min_quality_score": 0.75}
    body.update(kw)
    return client.post("/agents", headers=auth, json=body).json()


def _events(n, latency, override=False, quality=0.9):
    return [{"latency_ms": latency, "cost_usd": 0.002, "quality_score": quality,
             "human_override": override, "decided_by": "llm"} for _ in range(n)]


def test_register_and_scorecard():
    with TestClient(app) as client:
        auth = _signup(client)
        agent = _register(client, auth)
        client.post(f"/agents/{agent['id']}/events/batch", headers=auth,
                    json=_events(10, 500))
        sc = client.get(f"/agents/{agent['id']}/scorecard", headers=auth).json()
        assert sc["queries"] == 10
        assert sc["latency_p99_ms"] == 500.0
        assert sc["slo_latency_ok"] is True
        assert round(sc["cost_per_query_usd"], 3) == 0.002


def test_latency_slo_breach_creates_alert():
    with TestClient(app) as client:
        auth = _signup(client)
        agent = _register(client, auth, slo_p99_latency_ms=1000)
        client.post(f"/agents/{agent['id']}/events/batch", headers=auth,
                    json=_events(20, 5000))   # way over SLO
        out = client.post(f"/agents/{agent['id']}/evaluate", headers=auth).json()
        assert "latency_p99" in out["kinds"]
        alerts = client.get("/alerts", headers=auth).json()
        assert any(a["kind"] == "latency_p99" and a["severity"] == "critical" for a in alerts)


def test_override_spike_creates_alert():
    with TestClient(app) as client:
        auth = _signup(client)
        agent = _register(client, auth, max_override_rate=0.10)
        # 50% override rate, far above the 10% threshold.
        evs = _events(5, 300, override=True) + _events(5, 300, override=False)
        client.post(f"/agents/{agent['id']}/events/batch", headers=auth, json=evs)
        out = client.post(f"/agents/{agent['id']}/evaluate", headers=auth).json()
        assert "override_rate" in out["kinds"]


def test_alert_is_deduplicated():
    with TestClient(app) as client:
        auth = _signup(client)
        agent = _register(client, auth, slo_p99_latency_ms=1000)
        client.post(f"/agents/{agent['id']}/events/batch", headers=auth, json=_events(10, 5000))
        first = client.post(f"/agents/{agent['id']}/evaluate", headers=auth).json()
        second = client.post(f"/agents/{agent['id']}/evaluate", headers=auth).json()
        assert first["alerts_created"] == 1
        assert second["alerts_created"] == 0  # within dedup window


def test_overview_rolls_up_fleet():
    with TestClient(app) as client:
        auth = _signup(client)
        a1 = _register(client, auth, name="A1", kind="support")
        a2 = _register(client, auth, name="A2", kind="sdr")
        client.post(f"/agents/{a1['id']}/events/batch", headers=auth, json=_events(5, 300))
        client.post(f"/agents/{a2['id']}/events/batch", headers=auth, json=_events(3, 300))
        ov = client.get("/overview", headers=auth).json()
        assert ov["agent_count"] == 2
        assert ov["total_queries"] == 8
        assert len(ov["scorecards"]) == 2


def test_compliance_report_generates_markdown():
    with TestClient(app) as client:
        auth = _signup(client)
        agent = _register(client, auth, kind="claims", risk_category="high")
        client.post(f"/agents/{agent['id']}/events/batch", headers=auth,
                    json=_events(10, 400, override=True))
        rep = client.get(f"/agents/{agent['id']}/compliance-report", headers=auth).json()
        md = rep["markdown"]
        assert "Compliance Report" in md
        assert "high" in md                      # risk category rendered
        assert "Human oversight" in md
        assert "Explainability" in md


def test_tenant_isolation():
    with TestClient(app) as client:
        a = _signup(client)
        b = _signup(client)
        agent = _register(client, a)
        # Tenant B cannot see A's agent, ingest to it, or report on it.
        assert client.get(f"/agents/{agent['id']}/scorecard", headers=b).status_code == 404
        assert client.post(f"/agents/{agent['id']}/events", headers=b,
                           json={"latency_ms": 1}).status_code == 404
        assert client.get(f"/agents/{agent['id']}/compliance-report",
                          headers=b).status_code == 404
        assert client.get("/agents", headers=b).json() == []
