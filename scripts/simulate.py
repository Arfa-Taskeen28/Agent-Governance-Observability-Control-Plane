"""Populate the control plane with realistic 14-day telemetry for the four
portfolio agents, so the dashboard, scorecards, trends, alerts, and compliance
reports all light up offline — no live agents required.

Bakes in two governance events on purpose:
- the SDR agent has a latency regression in the last few days (p99 SLO breach),
- the claims agent has an override-rate spike (human oversight kicking in).

    python scripts/simulate.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import random
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

random.seed(7)

# name, kind, risk, slo_p99_ms, max_override, min_quality, base latency, base cost, base quality
AGENTS = [
    ("Customer Support Agent", "support", "limited", 2500, 0.25, 0.75, 700, 0.004, 0.90),
    ("Sales SDR Agent", "sdr", "limited", 2000, 0.30, 0.70, 900, 0.006, 0.86),
    ("Document Intelligence Agent", "docintel", "high", 4000, 0.35, 0.80, 1500, 0.010, 0.92),
    ("Claims Triage Agent", "claims", "high", 3000, 0.20, 0.85, 1100, 0.008, 0.88),
]


def _req(base_url, path, payload=None, token=None, method="POST"):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - local demo target
        return json.loads(resp.read())


def _gen_events(kind: str, days: int = 14) -> list[dict]:
    base = dict(zip(
        ["latency", "cost", "quality"],
        {r[1]: (r[6], r[7], r[8]) for r in AGENTS}[kind], strict=True,
    ))
    now = datetime.now(UTC)
    events: list[dict] = []
    for d in range(days):
        day = now - timedelta(days=days - 1 - d)
        n = random.randint(40, 90)
        for _ in range(n):
            latency = max(50, int(random.gauss(base["latency"], base["latency"] * 0.3)))
            override = random.random() < 0.08
            quality = min(1.0, max(0.4, random.gauss(base["quality"], 0.06)))

            # Injected governance events (last 3 days).
            if kind == "sdr" and d >= days - 3:
                latency = int(latency * 2.6)          # latency regression -> p99 SLO breach
            if kind == "claims" and d >= days - 3:
                override = random.random() < 0.40      # override spike -> oversight alert

            events.append({
                "occurred_at": (day + timedelta(minutes=random.randint(0, 1439))).isoformat(),
                "latency_ms": latency,
                "cost_usd": round(max(0.0005, random.gauss(base["cost"], base["cost"] * 0.2)), 6),
                "tokens": random.randint(200, 2000),
                "quality_score": round(quality, 3),
                "decided_by": random.choice(["llm", "code", "model"]),
                "human_override": override,
                "error": random.random() < 0.02,
                "trace_id": uuid.uuid4().hex[:16],
            })
    return events


def main(base_url: str) -> None:
    tenant = _req(base_url, "/tenants/signup", {"name": f"AcmeAI Ops {uuid.uuid4().hex[:6]}"})
    token = tenant["access_token"]
    print(f"tenant: {tenant['tenant_id']}\ntoken:  {token}\n")

    for name, kind, risk, slo, over, qual, *_ in AGENTS:
        agent = _req(base_url, "/agents", {
            "name": name, "kind": kind, "risk_category": risk,
            "slo_p99_latency_ms": slo, "max_override_rate": over, "min_quality_score": qual,
        }, token=token)
        events = _gen_events(kind)
        # Ingest in chunks to keep request bodies reasonable.
        for i in range(0, len(events), 200):
            _req(base_url, f"/agents/{agent['id']}/events/batch", events[i:i + 200], token=token)
        result = _req(base_url, f"/agents/{agent['id']}/evaluate", token=token)
        print(f"{name:30} events={len(events):4} alerts={result['kinds'] or '-'}")

    ov = _req(base_url, "/overview", token=token, method="GET")
    print(f"\nfleet: {ov['agent_count']} agents · {ov['total_queries']} queries · "
          f"${ov['total_cost_usd']} · {ov['agents_breaching_slo']} breaching SLO")
    print("\nOpen the dashboard at the base URL to explore scorecards, trends, "
          "alerts, and compliance reports.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    main(parser.parse_args().base_url)
