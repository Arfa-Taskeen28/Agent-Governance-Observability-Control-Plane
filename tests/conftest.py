"""Test configuration. Point the app at a SQLite DB and dummy secret *before*
any app module (and its cached settings) is imported, so tests run with no
external Postgres/Redis/LLM dependencies."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test_control.sqlite")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    import app.db.models  # noqa: F401 - register models on the metadata
    from app.db.base import Base, engine

    Base.metadata.create_all(bind=engine)
    yield
