"""Provider wrapper tests. No network: Gemini is tested only on message conversion."""

import json

import pytest
from google.genai import types

import agent.llm.gemini as gemini_mod
from agent.llm.base import Message, ToolCall
from agent.llm.gemini import _from_response, _to_contents
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


def test_gemini_pacing_spaces_calls(monkeypatch):
    # Fake key: creating the client makes no network call.
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("LLM_MAX_RPM", "12")
    clock = {"now": 100.0}
    slept: list[float] = []
    monkeypatch.setattr(gemini_mod.time, "monotonic", lambda: clock["now"])

    def fake_sleep(s: float) -> None:
        slept.append(s)
        clock["now"] += s

    monkeypatch.setattr(gemini_mod.time, "sleep", fake_sleep)
    llm = gemini_mod.GeminiLLM(model="gemini-3.1-flash-lite")
    llm._pace()  # first call: no wait
    clock["now"] += 1.0
    llm._pace()  # 60/12 = 5 s interval, 1 s already passed
    assert slept == [pytest.approx(4.0)]


def test_gemini_no_pacing_by_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-a-real-key")
    monkeypatch.delenv("LLM_MAX_RPM", raising=False)
    assert gemini_mod.GeminiLLM(model="m")._min_interval_s == 0.0


def test_gemini_empty_response_becomes_empty_message():
    assert _from_response(types.GenerateContentResponse(candidates=[])).content == ""
