"""Google Gemini provider (google-genai SDK, API key auth)."""

import json
import os

from google import genai
from google.genai import types

from agent.llm.base import LLMResponse, Message, ToolCall, ToolSpec
from agent.llm.pacing import Pacer


class GeminiLLM:
    provider = "gemini"

    def __init__(self, model: str, timeout_s: float = 30.0):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Put it in .env or the environment.")
        self.model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000),  # milliseconds
                # The SDK does not retry unless asked. Retry rate limits (429) and
                # transient 5xx with backoff; failed requests are not billed. Waits of
                # ~4+8+16+30 s ride out short "model overloaded" 503 spikes.
                retry_options=types.HttpRetryOptions(attempts=5, initial_delay=4.0, max_delay=30.0),
            ),
        )
        self._pacer = Pacer()

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> LLMResponse:
        self._pacer.wait()
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters_json_schema=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ],
            # The agent loop runs tools itself, so it can count and limit them.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        resp = self._client.models.generate_content(
            model=self.model, contents=_to_contents(messages), config=config
        )
        usage = resp.usage_metadata
        return LLMResponse(
            message=_from_response(resp),
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            # Thinking tokens are billed as output.
            output_tokens=(
                (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
                if usage
                else 0
            ),
        )


def _to_contents(messages: list[Message]) -> list[types.Content]:
    contents: list[types.Content] = []
    for m in messages:
        if m.role == "user":
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=m.content)])
            )
        elif m.role == "assistant":
            if m.raw is not None:
                contents.append(m.raw)
                continue
            parts = [types.Part.from_text(text=m.content)] if m.content else []
            parts += [
                types.Part(function_call=types.FunctionCall(id=c.id, name=c.name, args=c.args))
                for c in m.tool_calls
            ]
            contents.append(types.Content(role="model", parts=parts))
        else:
            part = types.Part(
                function_response=types.FunctionResponse(
                    id=m.tool_call_id, name=m.name, response={"output": _as_json(m.content)}
                )
            )
            # Answers to parallel calls must share one turn.
            last = contents[-1] if contents else None
            if last is not None and last.role == "user" and last.parts[0].function_response:
                last.parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return contents


def _from_response(resp: types.GenerateContentResponse) -> Message:
    if not resp.candidates or resp.candidates[0].content is None:
        return Message(role="assistant", content="")
    content = resp.candidates[0].content
    parts = content.parts or []
    text = "".join(p.text for p in parts if p.text and not p.thought)
    calls = [
        ToolCall(
            id=p.function_call.id or f"call_{i}",
            name=p.function_call.name or "",
            args=dict(p.function_call.args or {}),
        )
        for i, p in enumerate(parts)
        if p.function_call
    ]
    return Message(role="assistant", content=text, tool_calls=calls, raw=content)


def _as_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
