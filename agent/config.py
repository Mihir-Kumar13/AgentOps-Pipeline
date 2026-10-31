"""Runtime settings, read from environment variables.

A git-ignored `.env` at the repo root is loaded for local runs. Real environment
variables win over `.env`, so CI and Kubernetes never depend on that file.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Limits:
    """Hard limits from CLAUDE.md section 5. The loop alert watches these too."""

    max_tool_calls: int = 8
    max_replans: int = 3
    timeout_s: float = 60.0


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    mock_tools_url: str
    limits: Limits
    release: str


DEFAULT_MODELS = {
    "mock": "mock-heuristic-v1",
    "gemini": "gemini-3.1-flash-lite",
    "openai": "gpt-5-nano",
}


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    return Settings(
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider, ""),
        mock_tools_url=os.getenv("MOCK_TOOLS_URL", "http://localhost:8081"),
        limits=Limits(),
        release=os.getenv("AGENT_RELEASE", "stable"),
    )
