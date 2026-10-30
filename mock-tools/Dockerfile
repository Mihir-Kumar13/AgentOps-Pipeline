# mock-tools API. Build from the repo root:
#   docker build -f mock-tools/Dockerfile -t mock-tools .
FROM ghcr.io/astral-sh/uv:0.11.28 AS uv

FROM python:3.12.13-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# Shared deps only: no LLM SDKs in this image.
RUN uv sync --frozen --no-default-groups

FROM python:3.12.13-slim-bookworm
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    SCENARIOS_PATH=/app/data/scenarios.jsonl
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY mock-tools/mock_tools/ mock_tools/
COPY evals/dataset/scenarios.jsonl data/scenarios.jsonl
RUN useradd --system --uid 10001 app
USER 10001
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8081/healthz')"]
CMD ["uvicorn", "mock_tools.app:app", "--host", "0.0.0.0", "--port", "8081"]
