"""Process-wide singletons for the control plane."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.llm.client import LLMClient


@lru_cache
def get_llm_or_none() -> LLMClient | None:
    s = get_settings()
    has_key = (s.llm_provider == "anthropic" and s.anthropic_api_key) or (
        s.llm_provider == "openai" and s.openai_api_key
    )
    return LLMClient() if has_key else None
