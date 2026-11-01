# Metrics contract

> Single source of truth for span, attribute and metric names (CLAUDE.md section 7).
> The same names are used by the Grafana dashboard (Phase 2), the PR eval gate (Phase 6)
> and the canary analysis (Phase 7). Change a name here **and** in
> `agent/telemetry/instruments.py`, `observability/alerts/agent-rules.yml` and
> `observability/dashboards/agent.json`, or not at all.

## Spans (OTel GenAI conventions)

```
invoke_agent triage-agent            one per run              (kind INTERNAL)
├── chat <model>                     one per LLM call         (kind CLIENT)
└── execute_tool <tool>              one per tool call        (kind INTERNAL)
    └── POST /tools/<tool>           mock-tools HTTP request, joined via W3C traceparent
```

| Attribute | On span | Meaning |
|---|---|---|
| `gen_ai.operation.name` | all | `invoke_agent`, `chat`, `execute_tool` |
| `gen_ai.agent.name` | invoke_agent | `triage-agent` |
| `gen_ai.provider.name` | invoke_agent, chat | `openai`, `gcp.gemini`, `mock`, `scripted` |
| `gen_ai.request.model` | invoke_agent, chat | for example `gpt-5-nano` |
| `gen_ai.usage.input_tokens` / `output_tokens` | invoke_agent (run total), chat (per call) | tokens; output includes reasoning tokens |
| `gen_ai.tool.name`, `gen_ai.tool.call.id` | execute_tool | tool name and the model's call id |
| `error.type` | any span with an error | run: its status (for example `replan_limit`); tool: `tool_error`, `duplicate_call`, `unknown_tool`; chat: exception class |
| `app.agent.cost_usd` | invoke_agent | run cost at paid-tier prices (`agent/llm/pricing.py`) |
| `app.agent.tool_calls` | invoke_agent | tool calls in the run, including failed ones |
| `app.agent.replans` | invoke_agent | turns the model had to redo (ADR-006) |
| `app.agent.prompt_version` | invoke_agent | header of `agent/prompts/triage_system.md` |
| `app.agent.release` | invoke_agent | `stable` or `canary` (env `AGENT_RELEASE`) |
| `app.agent.status` | invoke_agent | `ok`, `invalid_output`, `tool_limit`, `replan_limit`, `timeout`, `error` |
| `app.alert.id` | invoke_agent | input alert id |

## Prometheus metrics (sent directly by the agent)

Every metric has the `release` label. Counters start at 0 for every known label set when
the agent starts, so the first run is not lost to Prometheus.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `agent_runs_total` | counter | `release`, `status`, `prompt_version`, `model` | finished runs |
| `agent_run_cost_usd` | histogram | `release` | cost per run; buckets $0.0001 … $0.1 |
| `agent_run_duration_seconds` | histogram | `release` | wall-clock per run; buckets 0.5 s … 60 s |
| `agent_tool_calls_total` | counter | `release`, `tool` | tool calls (the denominator for the tool error rate) |
| `agent_tool_errors_total` | counter | `release`, `tool` | **real** tool failures only (HTTP/transport). Loops and unknown tools are not counted |
| `agent_loops_total` | counter | `release` | runs stopped with `tool_limit` or `replan_limit` |
| `agent_output_valid_total` | counter | `release`, `valid` (`true`/`false`) | runs with or without a schema-valid report |

Also present, from the Collector's spanmetrics connector: `traces_span_metrics_calls_total` and
`traces_span_metrics_duration_milliseconds_*`, labelled by `span_name` (per-step latency).

## Derived rates (used in alerts, gate and dashboard)

| Rate | PromQL (per release) | Alert threshold |
|---|---|---|
| Cost per run | `rate(agent_run_cost_usd_sum) / rate(agent_run_cost_usd_count)` | > 3× the 1-hour value |
| Loop rate | `rate(agent_loops_total) / rate(agent_runs_total)` | > 5% |
| Tool error rate | `rate(agent_tool_errors_total) / rate(agent_tool_calls_total)` | > 5% |
| Invalid output rate | `rate(agent_output_valid_total{valid="false"}) / rate(agent_output_valid_total)` | > 2% |
| Success rate | `rate(agent_runs_total{status="ok"}) / rate(agent_runs_total)` | dashboard only |

All alerts use `for: 2m`. Rules: `observability/alerts/agent-rules.yml`; tests: `make alerts-test`.

## Logs (Loki)

One log line per run, `triage run finished`, from logger `agent.run`. Attributes: `alert_id`,
`status`, `model`, `cost_usd`, `latency_s`, `tool_calls`, `severity`, `probable_cause`, and
`trace_id` / `span_id`, so Grafana can jump from a log line to its trace. Select with `{service_name="triage-agent"}`.
