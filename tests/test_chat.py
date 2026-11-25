import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm_service
from app.config import get_settings
from app.main import create_app
from app.services.llm import LLMError, LLMResult

settings = get_settings()


class FakeLLM:
    def __init__(self) -> None:
        self.error: LLMError | None = None
        self.calls: list[tuple[str, int]] = []

    async def generate(self, prompt: str, *, max_output_tokens: int) -> LLMResult:
        self.calls.append((prompt, max_output_tokens))
        if self.error:
            raise self.error
        return LLMResult(text="pong", model="fake-model", input_tokens=4, output_tokens=2)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(fake_llm: FakeLLM) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    return TestClient(app)


def test_chat_success(client: TestClient) -> None:
    response = client.post("/v1/chat", json={"prompt": "ping"})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "pong"
    assert body["model"] == "fake-model"
    assert body["usage"] == {"input_tokens": 4, "output_tokens": 2}
    assert isinstance(body["latency_ms"], int)


def test_chat_uses_default_token_limit(client: TestClient, fake_llm: FakeLLM) -> None:
    client.post("/v1/chat", json={"prompt": "ping"})
    assert fake_llm.calls == [("ping", settings.default_max_output_tokens)]


def test_chat_passes_smaller_token_limit_through(client: TestClient, fake_llm: FakeLLM) -> None:
    client.post("/v1/chat", json={"prompt": "ping", "max_output_tokens": 10})
    assert fake_llm.calls == [("ping", 10)]


def test_chat_clamps_token_limit_to_cap(client: TestClient, fake_llm: FakeLLM) -> None:
    client.post("/v1/chat", json={"prompt": "ping", "max_output_tokens": 10_000_000})
    assert fake_llm.calls == [("ping", settings.max_output_tokens_cap)]


def test_chat_rejects_overlong_prompt(client: TestClient, fake_llm: FakeLLM) -> None:
    prompt = "a" * (settings.max_prompt_chars + 1)
    response = client.post("/v1/chat", json={"prompt": prompt})
    assert response.status_code == 422
    assert fake_llm.calls == []


@pytest.mark.parametrize("payload", [{}, {"prompt": ""}, {"prompt": "   "}])
def test_chat_rejects_missing_or_blank_prompt(client: TestClient, payload: dict) -> None:
    assert client.post("/v1/chat", json=payload).status_code == 422


def test_chat_rejects_non_positive_token_limit(client: TestClient) -> None:
    response = client.post("/v1/chat", json={"prompt": "ping", "max_output_tokens": 0})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("status", "message"),
    [(502, "LLM upstream error"), (504, "LLM request timed out"), (503, "not configured")],
)
def test_chat_maps_llm_errors(
    client: TestClient, fake_llm: FakeLLM, status: int, message: str
) -> None:
    fake_llm.error = LLMError(status, message)
    response = client.post("/v1/chat", json={"prompt": "ping"})
    assert response.status_code == status
    assert response.json() == {"detail": message}
