"""Request and response models for the public API."""

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    # Optional. The server clamps this to its configured cap.
    max_output_tokens: int | None = Field(default=None, ge=1)

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    text: str
    model: str
    usage: TokenUsage
    latency_ms: int
