"""Run the triage agent on the eval dataset and print per-category scores.

    uv run python -m evals.runner --n 3 --split all [--out results/x.json]

LLM provider/model come from LLM_PROVIDER / LLM_MODEL (see agent/config.py).
mock-tools runs in-process by default (no server needed); set MOCK_TOOLS_URL to use
a running one instead (for example the docker compose stack).

Exit codes: 0 finished, 2 aborted because spend reached EVAL_MAX_USD.
"""

import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from agent.app.graph import TriageAgent
from agent.app.schemas import Alert
from agent.app.tools import ToolClient
from agent.config import REPO_ROOT, load_settings
from agent.llm import get_llm
from agent.prompts import load_prompt
from agent.telemetry import setup_telemetry
from evals.scorers.deterministic import score_run

DATASET = REPO_ROOT / "evals/dataset/scenarios.jsonl"
RAW_DIR = REPO_ROOT / "results/raw"


def load_scenarios(split: str, ids: list[str] | None = None) -> list[dict]:
    rows = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    if split != "all":
        rows = [s for s in rows if s["split"] == split]
    if ids:
        rows = [s for s in rows if s["id"] in ids]
    return rows


def tools_http() -> httpx.Client:
    url = os.getenv("MOCK_TOOLS_URL")
    if url:
        return httpx.Client(base_url=url, timeout=10.0)
    # In-process: same FastAPI app, no network, no server to start.
    sys.path.insert(0, str(REPO_ROOT / "mock-tools"))
    from fastapi.testclient import TestClient
    from mock_tools.app import app

    return TestClient(app)


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile; fine for the small samples we have."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def summarize(records: list[dict]) -> dict:
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_cat[r["category"]].append(r)

    def block(rs: list[dict]) -> dict:
        return {
            "runs": len(rs),
            "quality": round(sum(r["score"]["quality"] for r in rs) / len(rs), 4),
            "pass_rate": round(sum(r["score"]["passed"] for r in rs) / len(rs), 4),
        }

    runs = [r["run"] for r in records]
    n_calls = sum(len(r["tool_calls"]) for r in runs)
    safety = [r for r in records if r["safety"]]
    return {
        "overall": block(records),
        "by_category": {cat: block(rs) for cat, rs in sorted(by_cat.items())},
        "safety_pass_rate": (
            round(sum(r["score"]["passed"] for r in safety) / len(safety), 4) if safety else None
        ),
        "cost_usd_total": round(sum(r["cost_usd"] for r in runs), 6),
        "cost_usd_per_run": round(sum(r["cost_usd"] for r in runs) / len(runs), 6),
        "input_tokens_total": sum(r["input_tokens"] for r in runs),
        "output_tokens_total": sum(r["output_tokens"] for r in runs),
        "latency_p50_s": percentile([r["latency_s"] for r in runs], 0.50),
        "latency_p95_s": percentile([r["latency_s"] for r in runs], 0.95),
        "tool_error_rate": round(sum(r["tool_errors"] for r in runs) / n_calls, 4)
        if n_calls
        else 0,
        "status_counts": dict(Counter(r["status"] for r in runs)),
    }


def print_table(summary: dict, meta: dict) -> None:
    print(
        f"\nprovider={meta['provider']} model={meta['model']} prompt={meta['prompt_version']} "
        f"N={meta['n']} split={meta['split']}"
    )
    print(f"{'category':<20}{'runs':>6}{'quality':>10}{'pass':>8}")
    for cat, b in summary["by_category"].items():
        print(f"{cat:<20}{b['runs']:>6}{b['quality']:>10.3f}{b['pass_rate']:>8.2f}")
    o = summary["overall"]
    print(f"{'OVERALL':<20}{o['runs']:>6}{o['quality']:>10.3f}{o['pass_rate']:>8.2f}")
    print(f"safety pass rate : {summary['safety_pass_rate']}")
    print(
        f"cost             : ${summary['cost_usd_total']:.6f} total, "
        f"${summary['cost_usd_per_run']:.6f}/run "
        f"({summary['input_tokens_total']} in / {summary['output_tokens_total']} out tokens)"
    )
    print(f"latency          : p50 {summary['latency_p50_s']}s, p95 {summary['latency_p95_s']}s")
    print(f"tool error rate  : {summary['tool_error_rate']}")
    print(f"statuses         : {summary['status_counts']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=3, help="repeats per scenario")
    ap.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    ap.add_argument("--ids", nargs="*", help="only these scenario ids")
    ap.add_argument("--out", type=Path, help="also write the result JSON here")
    args = ap.parse_args(argv)

    settings = load_settings()
    max_usd = float(os.getenv("EVAL_MAX_USD", "1.00"))
    prompt = load_prompt()
    telemetry = setup_telemetry()
    agent = TriageAgent(get_llm(settings), prompt, settings.limits, release=settings.release)
    scenarios = load_scenarios(args.split, args.ids)
    meta = {
        "provider": settings.llm_provider,
        "model": agent.llm.model,
        "prompt_version": prompt.version,
        "n": args.n,
        "split": args.split,
        "scenarios": len(scenarios),
        "eval_max_usd": max_usd,
        "release": settings.release,
        "telemetry": telemetry,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }

    records, spent, aborted = [], 0.0, False
    started = time.monotonic()
    with tools_http() as http:
        for s in scenarios:
            for rep in range(args.n):
                # Checked between runs, so the overshoot is at most one run's cost.
                if spent >= max_usd:
                    aborted = True
                    break
                alert = Alert(**s["alert"])
                run = agent.run(alert, ToolClient(http, alert.alert_id)).to_dict()
                spent += run["cost_usd"]
                records.append(
                    {
                        "scenario_id": s["id"],
                        "category": s["category"],
                        "split": s["split"],
                        "safety": s["safety"],
                        "repeat": rep,
                        "run": run,
                        "score": score_run(run, s["expected"], settings.limits),
                    }
                )
                mark = "PASS" if records[-1]["score"]["passed"] else "fail"
                print(
                    f"  {s['id']:<10} #{rep} {run['status']:<14} {mark}  "
                    f"q={records[-1]['score']['quality']:.2f} ${run['cost_usd']:.5f} "
                    f"{run['latency_s']}s",
                    flush=True,
                )
            if aborted:
                break

    meta["wall_clock_s"] = round(time.monotonic() - started, 2)
    meta["aborted_budget"] = aborted
    if not records:
        print("no runs executed")
        return 2 if aborted else 1
    summary = summarize(records)
    payload = {"meta": meta, "summary": summary, "records": records}

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_path = RAW_DIR / f"eval-{stamp}-{settings.llm_provider}.json"
    raw_path.write_text(json.dumps(payload, indent=2) + "\n")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + "\n")

    print_table(summary, meta)
    print(f"wall clock       : {meta['wall_clock_s']}s")
    print(
        f"saved            : {raw_path.relative_to(REPO_ROOT)}"
        + (f" and {args.out}" if args.out else "")
    )
    if aborted:
        print(f"ABORTED: spend reached EVAL_MAX_USD={max_usd}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
