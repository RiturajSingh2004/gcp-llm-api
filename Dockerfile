FROM python:3.12-slim

# uv binary from the official image. Pin a version tag here once you pick one.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /srv

# Dependencies first so this layer is cached until pyproject.toml or uv.lock changes.
# `--locked` fails the build if uv.lock is missing or out of date: run `uv lock` and commit it.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PORT=8080
EXPOSE 8080

# `exec` so uvicorn receives SIGTERM directly and shuts down cleanly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
