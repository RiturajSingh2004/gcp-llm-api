"""Thin wrapper around the Gemini SDK: timeout, error mapping, token counts.

Nothing here knows about FastAPI or settings, so it is easy to test with a
fake client.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class LLMError(Exception):
    """An LLM-side problem. `public_message` is safe to show to API clients."""

    def __init__(self, status_code: int, public_message: str) -> None:
        super().__init__(public_message)
        self.status_code = status_code
        self.public_message = public_message


class LLMService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        client: Any | None = None,
    ) -> None:
        self._model = model
        self._timeout = timeout_seconds
        if client is None and api_key:
            client = genai.Client(api_key=api_key)
        self._client = client

    async def generate(self, prompt: str, *, max_output_tokens: int) -> LLMResult:
        if self._client is None:
            raise LLMError(503, "LLM backend is not configured")

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config={"max_output_tokens": max_output_tokens},
                ),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.warning("llm timeout", extra={"fields": {"timeout_seconds": self._timeout}})
            raise LLMError(504, "LLM request timed out") from None
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            logger.warning("llm api error", extra={"fields": {"upstream_code": code}})
            if code == 429:
                raise LLMError(429, "LLM rate limit reached") from exc
            raise LLMError(502, "LLM upstream error") from exc
        except Exception as exc:
            # Full traceback goes to the logs, never to the client.
            logger.exception("llm unexpected error")
            raise LLMError(502, "LLM upstream error") from exc

        text = getattr(response, "text", None)
        if not text:
            # Safety blocks and, on some models, "thinking" tokens eating a very
            # small max_output_tokens budget both show up as empty text.
            candidates = getattr(response, "candidates", None)
            finish_reason = None
            if candidates:
                finish_reason = str(getattr(candidates[0], "finish_reason", None))
            logger.warning("llm empty response", extra={"fields": {"finish_reason": finish_reason}})
            raise LLMError(502, "LLM returned no text")

        usage = getattr(response, "usage_metadata", None)
        return LLMResult(
            text=text,
            model=self._model,
            input_tokens=getattr(usage, "prompt_token_count", None) or 0,
            output_tokens=getattr(usage, "candidates_token_count", None) or 0,
        )
