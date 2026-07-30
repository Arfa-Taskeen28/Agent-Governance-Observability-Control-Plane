"""Application settings, loaded from environment. Single source of truth."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "agent-control-plane"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # --- Database (multi-tenant; every row is tenant-scoped) ---
    database_url: str = "postgresql+psycopg2://agent:agent@localhost:5432/agentdb"

    # --- Async workers ---
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM (optional; used only to narrate compliance summaries) ---
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_model: str = "claude-opus-4-8"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # --- Alerting ---
    # If set, threshold-breach alerts are POSTed here (Slack incoming webhook).
    slack_webhook_url: str = ""

    # --- Auth ---
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()
