"""Scorer edge cases. A wrong scorer silently breaks the gate, so test it hard."""

from evals.scorers.deterministic import score_run

EXPECTED = {
    "severity": "P2",
    "probable_cause": "oom",
    "required_tools": ["get_metrics", "get_logs", "create_ticket"],
    "forbidden_tools": [],
}


def call(name, error=None, **args):
    return {"name": name, "args": args, "error": error, "duplicate": False}


def good_run(**overrides):
    run = {
        "alert_id": "ALR-oom-01",
        "status": "ok",
        "report": {
            "severity": "P2",
            "probable_cause": "oom",
            "evidence": ["OOMKilled x2"],
            "recommended_action": "raise memory limit",
            "ticket_id": "TCK-ALR-oom-01",
        },
        "tool_calls": [call("get_metrics"), call("get_logs"), call("create_ticket")],
    }
    run.update(overrides)
    return run


def test_perfect_run_passes():
    result = score_run(good_run(), EXPECTED)
    assert result["passed"] is True
    assert result["quality"] == 1.0


def test_wrong_severity_fails_one_check():
    run = good_run()
    run["report"]["severity"] = "P4"
    result = score_run(run, EXPECTED)
    assert result["checks"]["severity_match"] is False
    assert result["passed"] is False
    assert result["quality"] == 7 / 8


def test_missing_report_fails_schema_and_matches():
    result = score_run(good_run(report=None, status="invalid_output"), EXPECTED)
    checks = result["checks"]
    assert not checks["schema_valid"]
    assert not checks["severity_match"]
    assert not checks["cause_match"]
    assert not checks["ticket_consistent"]


def test_schema_invalid_report():
    run = good_run()
    run["report"]["severity"] = "SEV1"
    assert score_run(run, EXPECTED)["checks"]["schema_valid"] is False


def test_failed_tool_call_does_not_count_as_called():
    calls = [call("get_metrics"), call("get_logs", error="HTTP 500"), call("create_ticket")]
    assert score_run(good_run(tool_calls=calls), EXPECTED)["checks"]["required_tools"] is False


def test_forbidden_tool_called():
    expected = {**EXPECTED, "required_tools": [], "forbidden_tools": ["create_ticket"]}
    assert score_run(good_run(), expected)["checks"]["forbidden_tools"] is False


def test_duplicate_calls_are_loops():
    calls = [
        call("get_metrics", w="1h"),
        call("get_metrics", w="1h"),
        call("get_logs"),
        call("create_ticket"),
    ]
    assert score_run(good_run(tool_calls=calls), EXPECTED)["checks"]["no_loops"] is False


def test_same_tool_different_args_is_not_a_loop():
    calls = [
        call("get_metrics", w="1h"),
        call("get_metrics", w="6h"),
        call("get_logs"),
        call("create_ticket"),
    ]
    assert score_run(good_run(tool_calls=calls), EXPECTED)["checks"]["no_loops"] is True


def test_too_many_tool_calls():
    calls = [call("get_metrics", w=f"{i}m") for i in range(9)]
    assert score_run(good_run(tool_calls=calls), EXPECTED)["checks"]["tool_budget"] is False


def test_ticket_id_must_match_created_ticket():
    run = good_run()
    run["report"]["ticket_id"] = "TCK-made-up"
    assert score_run(run, EXPECTED)["checks"]["ticket_consistent"] is False


def test_ticket_id_must_be_null_without_ticket():
    run = good_run(tool_calls=[call("get_metrics")])
    assert score_run(run, EXPECTED)["checks"]["ticket_consistent"] is False
