"""FastAPI dependencies. Tests override `get_llm_service` with a fake."""

from functools import lru_cache

from app.config import get_settings
from app.services.llm import LLMService


@lru_cache
def get_llm_service() -> LLMService:
    settings = get_settings()
    api_key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    return LLMService(
        api_key=api_key or None,
        model=settings.gemini_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
