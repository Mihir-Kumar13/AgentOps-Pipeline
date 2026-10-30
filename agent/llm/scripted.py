"""Test double that replays a fixed list of responses, one per chat() call."""

from agent.llm.base import LLMResponse, Message, ToolSpec


class ScriptedLLM:
    provider = "scripted"
    model = "scripted"

    def __init__(self, responses: list[Message]):
        self._responses = list(responses)
        self.calls = 0

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
        if self.calls >= len(self._responses):
            raise RuntimeError("ScriptedLLM ran out of responses")
        msg = self._responses[self.calls]
        self.calls += 1
        return LLMResponse(message=msg, input_tokens=10, output_tokens=5)
