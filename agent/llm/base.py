"""Provider-neutral message types and the LLM client interface.

The agent only speaks these types, so swapping Gemini for the mock (or another
provider later) never touches the agent loop.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # For role="tool": which call this answers.
    tool_call_id: str | None = None
    name: str | None = None
    # Provider-native copy of an assistant turn. Gemini needs it replayed as-is
    # so its "thought signatures" survive multi-step tool calling.
    raw: Any = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments


@dataclass
class LLMResponse:
    message: Message
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    provider: str
    model: str

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMResponse: ...
