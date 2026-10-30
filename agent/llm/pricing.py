"""USD prices per 1M tokens, used to compute `cost_usd` per run.

Source: https://ai.google.dev/gemini-api/docs/pricing (paid tier, standard, text),
checked 2026-10-31. Output prices include thinking tokens. Re-check before trusting
cost numbers; prices for some models change on 2027-01-01.
"""

PRICES_PER_M: dict[str, tuple[float, float]] = {
    # model: (input, output)
    "mock-heuristic-v1": (0.0, 0.0),
    "scripted": (0.0, 0.0),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.6-flash": (0.75, 3.75),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Raise on unknown models: a silent $0 would let cost regressions through the gate."""
    if model not in PRICES_PER_M:
        raise KeyError(f"no price for model {model!r}; add it to agent/llm/pricing.py")
    price_in, price_out = PRICES_PER_M[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
