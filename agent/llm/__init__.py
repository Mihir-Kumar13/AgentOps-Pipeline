"""LLM provider wrapper. Pick the provider with the LLM_PROVIDER env var."""

from agent.config import Settings
from agent.llm.base import LLMClient


def get_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "mock":
        from agent.llm.mock import MockLLM

        return MockLLM()
    if settings.llm_provider == "gemini":
        from agent.llm.gemini import GeminiLLM

        return GeminiLLM(model=settings.llm_model)
    if settings.llm_provider == "openai":
        from agent.llm.openai_provider import OpenAILLM

        return OpenAILLM(model=settings.llm_model)
    raise ValueError(
        f"unknown LLM_PROVIDER {settings.llm_provider!r} (supported: mock, gemini, openai)"
    )
