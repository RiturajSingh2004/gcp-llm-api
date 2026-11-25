"""LLMService tests with a fake SDK client. No network, no FastAPI needed."""

import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from app.services.llm import LLMError, LLMService


def make_client(handler):
    models = SimpleNamespace(generate_content=handler)
    return SimpleNamespace(aio=SimpleNamespace(models=models))


def make_response(text="hi", prompt_tokens=3, output_tokens=2):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=output_tokens,
        ),
        candidates=[SimpleNamespace(finish_reason="STOP")],
    )


def make_service(handler, timeout=1.0):
    return LLMService(
        api_key=None,
        model="test-model",
        timeout_seconds=timeout,
        client=make_client(handler),
    )


def generate(service, prompt="hello", max_output_tokens=50):
    return asyncio.run(service.generate(prompt, max_output_tokens=max_output_tokens))


class FakeAPIError(genai_errors.APIError):
    """Skips the SDK constructor so the test does not depend on its signature."""

    def __init__(self, code: int) -> None:
        Exception.__init__(self, f"fake upstream {code}")
        self.code = code


def test_generate_returns_text_and_usage():
    async def handler(**kwargs):
        assert kwargs["model"] == "test-model"
        assert kwargs["contents"] == "hello"
        assert kwargs["config"]["max_output_tokens"] == 50
        return make_response()

    result = generate(make_service(handler))
    assert result.text == "hi"
    assert result.model == "test-model"
    assert (result.input_tokens, result.output_tokens) == (3, 2)


def test_missing_usage_metadata_counts_as_zero():
    async def handler(**kwargs):
        response = make_response()
        response.usage_metadata = None
        return response

    result = generate(make_service(handler))
    assert (result.input_tokens, result.output_tokens) == (0, 0)


def test_not_configured_is_503():
    service = LLMService(api_key=None, model="m", timeout_seconds=1.0)
    with pytest.raises(LLMError) as exc_info:
        generate(service)
    assert exc_info.value.status_code == 503


def test_timeout_is_504():
    async def handler(**kwargs):
        await asyncio.sleep(5)

    with pytest.raises(LLMError) as exc_info:
        generate(make_service(handler, timeout=0.01))
    assert exc_info.value.status_code == 504


@pytest.mark.parametrize(("upstream", "expected"), [(429, 429), (500, 502), (403, 502)])
def test_api_errors_are_mapped(upstream, expected):
    async def handler(**kwargs):
        raise FakeAPIError(upstream)

    with pytest.raises(LLMError) as exc_info:
        generate(make_service(handler))
    assert exc_info.value.status_code == expected


def test_unexpected_exception_is_502_without_leaking_details():
    async def handler(**kwargs):
        raise RuntimeError("secret-internal-detail")

    with pytest.raises(LLMError) as exc_info:
        generate(make_service(handler))
    assert exc_info.value.status_code == 502
    assert "secret-internal-detail" not in exc_info.value.public_message


def test_empty_text_is_502():
    async def handler(**kwargs):
        return make_response(text=None)

    with pytest.raises(LLMError) as exc_info:
        generate(make_service(handler))
    assert exc_info.value.status_code == 502
