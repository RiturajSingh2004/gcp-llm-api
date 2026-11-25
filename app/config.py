"""Environment-driven settings.

Locally these come from the environment or a `.env` file. On Cloud Run,
GEMINI_API_KEY is injected from Secret Manager as an env var, and the rest
are plain env vars set at deploy time.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Secret. Never log it, never bake it into the image.
    gemini_api_key: SecretStr | None = None

    # Verify the current free-tier Flash-class model in AI Studio before deploying
    # and override via the GEMINI_MODEL env var if this default is out of date.
    gemini_model: str = "gemini-3.5-flash-lite"

    log_level: str = "INFO"

    # Cost guards.
    max_prompt_chars: int = 4000
    default_max_output_tokens: int = 512
    max_output_tokens_cap: int = 1024
    llm_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
