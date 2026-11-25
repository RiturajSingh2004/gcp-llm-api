import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_llm_service
from app.config import Settings, get_settings
from app.schemas import ChatRequest, ChatResponse, TokenUsage
from app.services.llm import LLMError, LLMService

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]
LLMDep = Annotated[LLMService, Depends(get_llm_service)]


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    settings: SettingsDep,
    llm: LLMDep,
) -> ChatResponse:
    if len(body.prompt) > settings.max_prompt_chars:
        raise HTTPException(
            status_code=422,
            detail=f"prompt exceeds {settings.max_prompt_chars} characters",
        )

    # Server-side cap so a client cannot ask for an expensive response.
    max_output_tokens = min(
        body.max_output_tokens or settings.default_max_output_tokens,
        settings.max_output_tokens_cap,
    )

    started = time.perf_counter()
    try:
        result = await llm.generate(body.prompt, max_output_tokens=max_output_tokens)
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    # Read by the request-logging middleware in main.py.
    request.state.input_tokens = result.input_tokens
    request.state.output_tokens = result.output_tokens

    return ChatResponse(
        text=result.text,
        model=result.model,
        usage=TokenUsage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        ),
        latency_ms=latency_ms,
    )
