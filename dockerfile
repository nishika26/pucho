# syntax=docker/dockerfile:1
# Single image for both services (webhook + dashboard); docker-compose picks
# the command. Built with uv for fast, reproducible installs from uv.lock.

FROM python:3.13-slim

# uv binary (copied from the official image — no pip bootstrap needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first so this layer is cached unless the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Copy the application source.
COPY . .

# Default service: the FastAPI WhatsApp webhook. The dashboard service in
# docker-compose overrides this command.
EXPOSE 8000
CMD ["uv", "run", "main.py"]
