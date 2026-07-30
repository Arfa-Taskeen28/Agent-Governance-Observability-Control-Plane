# Agent Governance & Observability Control Plane

The capstone. A single dashboard that sits across every other agent in this
portfolio and answers the question every enterprise buyer eventually asks:
**"how do we know these agents are behaving correctly, and how do we prove it?"**
It aggregates cost-per-query, latency percentiles, quality scores, and
human-override rates per agent; alerts on SLO/governance threshold breaches; and
generates a **compliance report** per agent on demand.

Built on [`agent-platform-foundation`](../agent-platform-foundation) — same
multi-tenancy, audit-log, and observability spine.

## Why this is the differentiator

Nearly nine in ten agent projects never leave the workshop for production, and
the gap is almost always **operational maturity, not model quality**. Being able
to point at one dashboard and say "here's how I know all four of my other agents
are healthy, what they cost per query, and how often a human had to override
them" is exactly the maturity that separates production teams from prototypes.

## What it does

- **Per-agent scorecards** — queries, cost/query, latency **p50/p95/p99**, average
  quality score, **human-override rate**, error rate, each checked against the
  agent's SLO/governance thresholds.
- **Trends over time** — daily buckets so you can see drift (is quality slipping?
  is p99 latency creeping up?).
- **Threshold-breach alerts** — p99 over SLO, override-rate spike, quality below
  floor. Deduplicated, severity-tagged, and optionally pushed to **Slack**.
- **One-click compliance report** — a structured, non-technical-stakeholder
  markdown export per agent (risk classification, operational summary, quality,
  **human-oversight statistics**, explainability note, alert history). The single
  most enterprise-recognizable artifact in the portfolio.

## Architecture — telemetry ingestion, not cross-DB polling

```
Each agent emits an event per query  ──▶  POST /agents/{id}/events           [collector]
   { latency_ms, cost_usd, quality_score, human_override, decided_by, trace_id }
                    │
   aggregation  ──▶ per-agent scorecards (percentiles, cost/query, override rate)
                 ──▶ daily trends (drift)
                 ──▶ threshold evaluation ──▶ Alert rows ──▶ (Slack webhook)
                 ──▶ compliance report (markdown export)
                    │
   single dashboard at /  (fleet tiles · scorecards · trend chart · alerts · report)
```

**Why push, not pull.** Coupling a control plane to four separate databases is
fragile and can't observe agents that are asleep. Emitting telemetry to a
collector is how Langfuse / OpenTelemetry actually work, and it decouples the
plane from every agent's schema. An agent integrates in one line (a `POST` after
each query). For a demo with no live agents, [`scripts/simulate.py`](scripts/simulate.py)
generates 14 days of realistic telemetry for all four portfolio agents —
including a **latency regression** and an **override-rate spike** that trip real
alerts. (A pull/liveness adapter that pings each agent's `/health` is a natural
extension via the stored `base_url`.)

## The dashboard

Built with the repo's `dataviz` method: a **validated** categorical palette
(colorblind-safe, checked with the validator — CVD ΔE 24.2), reserved status
colors that always ship with an **icon + label** (never color alone), a
single-series p99-latency/override/cost **trend line chart** with a hover
crosshair + tooltip, and hero stat tiles for the fleet rollup.

## Runs fully offline (no API key)

Pure-Python metric aggregation (no numpy), SQLite, no LLM required. `make run`
then `make demo` fills the dashboard end-to-end with zero secrets.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest tests/unit -q            # 13 tests, no external services

make run                        # http://localhost:8000
make demo                       # seeds 4 agents + 14 days of telemetry + alerts

docker compose up --build       # full stack with Postgres + Redis
```

Open **http://localhost:8000/**: see the fleet tiles, click an agent to view its
trend, watch the SLO-breach alerts, and hit **"Compliance report"** to generate
and download a governance report.

### API

| Method | Path | Purpose |
|---|---|---|
| POST | `/tenants/signup` | Create a tenant (an org operating agents) |
| POST | `/agents` | Register a monitored agent (risk category + SLOs) |
| POST | `/agents/{id}/events` · `/events/batch` | Ingest telemetry |
| GET  | `/agents/{id}/scorecard` | Cost/latency/quality/override scorecard |
| GET  | `/agents/{id}/trend` | Daily trend for drift detection |
| POST | `/agents/{id}/evaluate` | Check thresholds → create/notify alerts |
| GET  | `/overview` | Fleet rollup (powers the dashboard) |
| GET  | `/alerts` | Recent threshold-breach alerts |
| GET  | `/agents/{id}/compliance-report` | Markdown report (`?download=true`) |

## Deploy live (Render, one blueprint)

The repo ships a [`render.yaml`](./render.yaml): **New → Blueprint → connect this
repo → Apply**. Set `SLACK_WEBHOOK_URL` in the Environment tab to receive alerts
in Slack. Then run `python scripts/simulate.py --base-url https://<your>.onrender.com`
to populate the live dashboard.

> Free-tier notes: the web service sleeps after ~15 min idle (~30s cold start);
> free Postgres expires after 90 days.

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy · Celery/Redis · structlog · Docker Compose ·
GitHub Actions · pytest. Pure-Python metric aggregation; validated dataviz palette.
