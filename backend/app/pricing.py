"""Pricing lookup for LLM token usage.

Prices live in ``pricing.yaml`` (USD per 1,000,000 tokens). The file is reloaded
on every call so operators can edit rates live without restarting the server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import yaml

_PRICING_PATH = os.path.join(os.path.dirname(__file__), "pricing.yaml")


@dataclass
class CostResult:
    """Outcome of a cost calculation.

    ``fallback`` is True when the model was not found in the rate card and the
    ``_default`` pricing was applied instead.
    """

    cost_usd: float
    fallback: bool


def _load_pricing() -> dict:
    """Read and parse pricing.yaml. Called per request so edits take effect live."""
    with open(_PRICING_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("models", {})


def cost_detail(model: str, prompt_tokens: int, completion_tokens: int) -> CostResult:
    """Compute cost and report whether the default rate was used."""
    models = _load_pricing()
    rate = models.get(model)
    fallback = False
    if rate is None:
        rate = models.get("_default", {"input": 0.0, "output": 0.0})
        fallback = True

    input_rate = float(rate.get("input", 0.0))
    output_rate = float(rate.get("output", 0.0))

    cost = (prompt_tokens / 1_000_000) * input_rate + (
        completion_tokens / 1_000_000
    ) * output_rate
    return CostResult(cost_usd=cost, fallback=fallback)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the USD cost for a request, falling back to ``_default`` pricing."""
    return cost_detail(model, prompt_tokens, completion_tokens).cost_usd
