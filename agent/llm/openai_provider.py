"""OpenAI provider (openai SDK, Chat Completions API, API key auth)."""

import json
import os

from openai import OpenAI
from openai.types.chat import ChatCompletion

from agent.llm.base import LLMResponse, Message, ToolCall, ToolSpec
from agent.llm.pacing import Pacer


class OpenAILLM:
    provider = "openai"

    def __init__(self, model: str, timeout_s: float = 30.0):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Put it in .env or the environment.")
        self.model = model
        # The SDK retries 429 and 5xx with backoff; failed requests are not billed.
        self._client = OpenAI(api_key=api_key, timeout=timeout_s, max_retries=4)
        self._pacer = Pacer()

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
        self._pacer.wait()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=_to_messages(system, messages),
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ],
        )
        usage = resp.usage
        return LLMResponse(
            message=_from_response(resp),
            input_tokens=usage.prompt_tokens if usage else 0,
            # completion_tokens already includes reasoning tokens, which are billed as output.
            output_tokens=usage.completion_tokens if usage else 0,
        )


def _to_messages(system: str, messages: list[Message]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            msg: dict = {"role": "assistant", "content": m.content or None}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args)},
                    }
                    for c in m.tool_calls
                ]
            out.append(msg)
        else:
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
    return out


def _from_response(resp: ChatCompletion) -> Message:
    if not resp.choices:
        return Message(role="assistant", content="")
    msg = resp.choices[0].message
    calls = [
        ToolCall(id=c.id, name=c.function.name, args=_parse_args(c.function.arguments))
        for c in msg.tool_calls or []
        if c.type == "function"
    ]
    return Message(role="assistant", content=msg.content or "", tool_calls=calls)


def _parse_args(raw: str) -> dict:
    """Malformed arguments are passed on as-is, so mock-tools rejects them as a tool error."""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_unparsed_arguments": raw}
    return value if isinstance(value, dict) else {"_unparsed_arguments": raw}
