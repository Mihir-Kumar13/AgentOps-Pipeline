# Costs

> Only real numbers, taken from the AWS bill, Cost Explorer, or the LLM provider's usage page.
> Estimates are marked **estimate** and listed separately.

## Per session (AWS)
| Date | Phase | What ran | Duration | Real cost (USD) | Source |
|---|---|---|---|---|---|
| 2026-10-31 | 0 | Nothing (local only) | n/a | 0.00 | No cloud resources used |
| 2026-11-01 | 1–2 | Nothing on AWS (local Docker only) | n/a | 0.00 | No cloud resources used |

## Per eval run (LLM)
| Date | Provider / model | Scenarios × N | Tokens in/out | Paid-tier equivalent (USD) | Actually billed | Notes |
|---|---|---|---|---|---|---|
| 2026-10-31 | mock / mock-heuristic-v1 | 20 × 3 | 26,934 / 3,801 (estimated) | 0.00 | $0 | Plumbing only, no API |
| 2026-10-31 | gemini / gemini-3.1-flash-lite | 5 × 1 | 27,050 / 1,126 | 0.008452 | $0 (free-tier key) | `results/phase1-baseline.json`. 1 run hit the free-tier 429 limit |
| 2026-10-31 | gemini / gemini-3.1-flash-lite | 1 × 1 (fa-01 re-run) | 5,169 / 155 | 0.001525 | $0 (free-tier key) | Check of the `LLM_MAX_RPM=12` pacing fix |
| 2026-10-31 | gemini / gemini-3.1-flash-lite | 20 × 1 | 70,650 / 2,902 | 0.022016 | $0 (free-tier key) | `results/phase1-gemini-full.json`: 11 answered, 9 got Google 503/504 |
| 2026-10-31 | gemini / gemini-3.1-flash-lite | 9-scenario re-run (stopped) + 1 check | 0 / 0 | 0.00 | $0 | Every call got 503 "high demand"; no tokens used |
| 2026-10-31 | openai / gpt-5-nano | 20 × 1 | 0 / 0 | 0.00 | $0 | Every call got 403: the project has no access to gpt-5-nano (only gpt-4o-mini allowed) |
| 2026-10-31 | openai / gpt-5-nano + gpt-4o-mini | 20 × 1 re-run + 3 test calls | ~20 / ~2 | <0.00001 | <$0.00001 | gpt-5-nano still 403 (listed but not callable); one gpt-4o-mini test call OK |
| 2026-10-31 | openai / gpt-4o-mini | 20 × 1 (+1 gpt-5-nano test call, 403) | 48,750 / 3,475 | 0.009397 | ~$0.0094 (paid key) | `results/phase1-openai-baseline.json`, the first complete real run |
| 2026-11-01 | openai / gpt-5-nano | 20 × 1 (+1 test call) | 69,434 / 63,101 | 0.028712 | ~$0.0287 (paid key) | `results/phase1-openai-gpt5nano.json`. Reasoning tokens make output about 3.1k per scenario |
| 2026-11-01 | openai / gpt-5-nano | 10 × 1 (Phase 2 telemetry run) | 37,330 / 31,011 | 0.014271 | ~$0.0143 (paid key) | `results/phase2-otel-run.json`. Monitoring stack is local Docker, $0 |

"Paid-tier equivalent" uses `agent/llm/pricing.py`, so it is what the run would cost on a paid key. The owner's key is free tier: the 429 error names the quota `generate_content_free_tier_requests`, limit 15/min.
Measured per scenario run: Gemini flash-lite about $0.0017–0.0020 (paid-tier equivalent), gpt-4o-mini $0.00047, gpt-5-nano $0.0014. A full 20 × N=3 eval on gpt-5-nano would be about **$0.09**.

## Estimates (before first apply)
_TBD (Phase 3)_
