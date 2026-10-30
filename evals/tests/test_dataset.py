"""Dataset integrity: catches broken or leaky scenarios before they reach the gate."""

import json
from collections import Counter
from typing import get_args

from agent.app.schemas import Alert, ProbableCause, Severity
from agent.app.tools import TOOL_NAMES
from evals.dataset.build_scenarios import SCENARIOS
from evals.runner import DATASET

CATEGORIES = {"oom", "bad_deploy", "db_saturation", "dependency_timeout", "false_alarm"}


def test_jsonl_is_up_to_date_with_builder():
    on_disk = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    assert on_disk == SCENARIOS, "run: uv run python -m evals.dataset.build_scenarios"


def test_ids_and_alert_ids_unique():
    assert len({s["id"] for s in SCENARIOS}) == len(SCENARIOS)
    assert len({s["alert"]["alert_id"] for s in SCENARIOS}) == len(SCENARIOS)


def test_scenarios_are_well_formed():
    for s in SCENARIOS:
        Alert(**s["alert"])
        exp = s["expected"]
        assert exp["severity"] in get_args(Severity)
        assert exp["probable_cause"] in get_args(ProbableCause)
        assert set(exp["required_tools"]) <= TOOL_NAMES
        assert not set(exp["required_tools"]) & set(exp["forbidden_tools"])
        assert s["split"] in {"dev", "holdout"}


def test_ticket_rule_matches_severity():
    for s in SCENARIOS:
        exp = s["expected"]
        if exp["severity"] in ("P1", "P2"):
            assert "create_ticket" in exp["required_tools"], s["id"]
        else:
            assert "create_ticket" in exp["forbidden_tools"], s["id"]


def test_every_category_in_both_splits():
    for split in ("dev", "holdout"):
        cats = {s["category"] for s in SCENARIOS if s["split"] == split}
        assert CATEGORIES | {"adversarial"} <= cats, split


def test_balanced_categories_and_safety_cases():
    counts = Counter(s["category"] for s in SCENARIOS)
    assert len({counts[c] for c in CATEGORIES}) == 1
    assert sum(s["safety"] for s in SCENARIOS) >= 3


def test_no_expected_answers_leak_into_tool_data():
    """mock_data is shown to the model; it must not carry the answer key."""
    for s in SCENARIOS:
        assert "expected" not in json.dumps(s["mock_data"])
