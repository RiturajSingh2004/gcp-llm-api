import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api import chat, health
from app.config import get_settings
from app.core.logging import setup_logging

request_logger = logging.getLogger("app.request")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="gcp-llm-api", version="0.1.0")

    @app.middleware("http")
    async def log_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        status_code = 500  # stays 500 if an unhandled exception escapes
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            fields: dict[str, object] = {
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
            # Token counts only exist for requests that reached the model.
            # The prompt itself is deliberately never logged.
            for key in ("input_tokens", "output_tokens"):
                value = getattr(request.state, key, None)
                if value is not None:
                    fields[key] = value
            request_logger.info("request", extra={"fields": fields})

    app.include_router(health.router)
    app.include_router(chat.router)
    return app


app = create_app()
