FROM ghcr.io/astral-sh/uv:0.13.4 AS uv
FROM python:3.13.11-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/worldweave/.venv

WORKDIR /opt/worldweave

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY backend ./backend

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
