# Costs

> Only real numbers, taken from the AWS bill, Cost Explorer, or the LLM provider's usage page.
> Estimates are marked **estimate** and listed separately.

## Per session (AWS)
| Date | Phase | What ran | Duration | Real cost (USD) | Source |
|---|---|---|---|---|---|
| 2026-10-31 | 0 | Nothing (local only) | n/a | 0.00 | No cloud resources used |

## Per eval run (LLM)
| Date | Provider / model | Scenarios × N | Tokens in/out | Paid-tier equivalent (USD) | Actually billed | Notes |
|---|---|---|---|---|---|---|
| 2026-10-31 | mock / mock-heuristic-v1 | 20 × 3 | 26,934 / 3,801 (estimated) | 0.00 | $0 | Plumbing only, no API |
| 2026-10-31 | gemini / gemini-3.1-flash-lite | 5 × 1 | 27,050 / 1,126 | 0.008452 | $0 (free-tier key) | `results/phase1-baseline.json`. 1 run hit the free-tier 429 limit |
| 2026-10-31 | gemini / gemini-3.1-flash-lite | 1 × 1 (fa-01 re-run) | 5,169 / 155 | 0.001525 | $0 (free-tier key) | Check of the `LLM_MAX_RPM=12` pacing fix |

"Paid-tier equivalent" uses `agent/llm/pricing.py`, so it is what the run would cost on a paid key. The owner's key is free tier: the 429 error names the quota `generate_content_free_tier_requests`, limit 15/min.
Projection from the real numbers above: about **$0.0017 per scenario run**, so a full 20 × N=3 eval would be about **$0.10** on a paid key.

## Estimates (before first apply)
_TBD (Phase 3)_
