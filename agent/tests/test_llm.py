"""Provider wrapper tests. No network: real providers are tested only on message conversion."""

import json

import pytest
from google.genai import types
from openai.types.chat import ChatCompletion

import agent.llm.gemini as gemini_mod
import agent.llm.pacing as pacing_mod
from agent.llm.base import Message, ToolCall
from agent.llm.gemini import _from_response, _to_contents
from agent.llm.openai_provider import OpenAILLM
from agent.llm.openai_provider import _from_response as oa_from_response
from agent.llm.openai_provider import _to_messages as oa_to_messages
from agent.llm.pricing import cost_usd
from agent.prompts import load_prompt


def test_prompt_has_version():
    prompt = load_prompt()
    assert prompt.version == "triage-v1"
    assert "Severity policy" in prompt.text


def test_cost_known_model():
    assert cost_usd("gemini-3.1-flash-lite", 1_000_000, 1_000_000) == pytest.approx(1.75)


def test_cost_unknown_model_raises():
    with pytest.raises(KeyError):
        cost_usd("no-such-model", 1, 1)


def test_gemini_parallel_tool_answers_share_one_turn():
    messages = [
        Message(role="user", content="alert"),
        Message(
            role="assistant",
            tool_calls=[ToolCall("a", "get_metrics", {}), ToolCall("b", "get_logs", {})],
        ),
        Message(role="tool", content=json.dumps({"x": 1}), tool_call_id="a", name="get_metrics"),
        Message(role="tool", content="plain text", tool_call_id="b", name="get_logs"),
    ]
    contents = _to_contents(messages)
    assert [c.role for c in contents] == ["user", "model", "user"]
    answers = contents[2].parts
    assert [p.function_response.name for p in answers] == ["get_metrics", "get_logs"]
    assert answers[0].function_response.response == {"output": {"x": 1}}
    assert answers[1].function_response.response == {"output": "plain text"}


def test_gemini_raw_content_is_replayed_unchanged():
    raw = types.Content(role="model", parts=[types.Part(text="hi", thought_signature=b"sig")])
    contents = _to_contents([Message(role="user", content="a"), Message(role="assistant", raw=raw)])
    assert contents[1] is raw


def test_gemini_response_parsing_skips_thoughts():
    resp = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="thinking...", thought=True),
                        types.Part(
                            function_call=types.FunctionCall(name="get_logs", args={"q": 1})
                        ),
                        types.Part(text="final"),
                    ],
                )
            )
        ]
    )
    msg = _from_response(resp)
    assert msg.content == "final"
    assert msg.tool_calls[0].name == "get_logs"
    assert msg.tool_calls[0].args == {"q": 1}
    assert msg.raw is resp.candidates[0].content


def test_pacing_spaces_calls(monkeypatch):
    clock = {"now": 100.0}
    slept: list[float] = []
    monkeypatch.setattr(pacing_mod.time, "monotonic", lambda: clock["now"])

    def fake_sleep(s: float) -> None:
        slept.append(s)
        clock["now"] += s

    monkeypatch.setattr(pacing_mod.time, "sleep", fake_sleep)
    monkeypatch.setenv("LLM_MAX_RPM", "12")
    pacer = pacing_mod.Pacer()
    pacer.wait()  # first call: no wait
    clock["now"] += 1.0
    pacer.wait()  # 60/12 = 5 s interval, 1 s already passed
    assert slept == [pytest.approx(4.0)]


def test_no_pacing_by_default(monkeypatch):
    monkeypatch.delenv("LLM_MAX_RPM", raising=False)
    assert pacing_mod.Pacer().min_interval_s == 0.0


def test_providers_build_without_network(monkeypatch):
    # Fake keys: creating the clients makes no network call.
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    assert gemini_mod.GeminiLLM(model="m").provider == "gemini"
    assert OpenAILLM(model="gpt-5-nano").provider == "openai"


def test_openai_missing_key_is_clear(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAILLM(model="gpt-5-nano")


def test_openai_message_conversion():
    messages = [
        Message(role="user", content="alert"),
        Message(role="assistant", tool_calls=[ToolCall("call_1", "get_logs", {"q": "x"})]),
        Message(role="tool", content='{"lines": []}', tool_call_id="call_1", name="get_logs"),
    ]
    out = oa_to_messages("SYSTEM", messages)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[0]["content"] == "SYSTEM"
    call = out[2]["tool_calls"][0]
    assert call["id"] == "call_1"
    assert json.loads(call["function"]["arguments"]) == {"q": "x"}
    assert out[2]["content"] is None
    assert out[3] == {"role": "tool", "tool_call_id": "call_1", "content": '{"lines": []}'}


def _completion(message: dict, usage: dict | None = None) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-5-nano",
            "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
            "usage": usage,
        }
    )


def test_openai_response_with_tool_calls():
    resp = _completion(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_9",
                    "type": "function",
                    "function": {"name": "get_metrics", "arguments": '{"service": "a"}'},
                },
                {
                    "id": "call_10",
                    "type": "function",
                    "function": {"name": "get_logs", "arguments": "{not json"},
                },
            ],
        }
    )
    msg = oa_from_response(resp)
    assert msg.content == ""
    assert [(c.id, c.name) for c in msg.tool_calls] == [
        ("call_9", "get_metrics"),
        ("call_10", "get_logs"),
    ]
    assert msg.tool_calls[0].args == {"service": "a"}
    # Broken JSON args are kept so mock-tools rejects them as a tool error.
    assert msg.tool_calls[1].args == {"_unparsed_arguments": "{not json"}


def test_openai_text_response():
    msg = oa_from_response(_completion({"role": "assistant", "content": '{"a": 1}'}))
    assert msg.content == '{"a": 1}'
    assert msg.tool_calls == []


def test_gemini_empty_response_becomes_empty_message():
    assert _from_response(types.GenerateContentResponse(candidates=[])).content == ""
