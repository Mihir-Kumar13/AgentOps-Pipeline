# triage-agent API. Build from the repo root:
#   docker build -f agent/Dockerfile -t triage-agent .
FROM ghcr.io/astral-sh/uv:0.11.28 AS uv

FROM python:3.12.13-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --group agent

FROM python:3.12.13-slim-bookworm
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY agent/ agent/
RUN useradd --system --uid 10001 app
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"]
CMD ["uvicorn", "agent.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
