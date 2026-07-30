"""Async tasks. Kept thin: the agent logic lives in app/, workers just schedule
and run it off the request path."""
from __future__ import annotations

from workers.celery_app import celery_app


@celery_app.task(name="workers.ping")
def ping() -> str:
    """Trivial task to verify broker connectivity in CI / smoke tests."""
    return "pong"
