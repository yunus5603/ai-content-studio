"""Cost estimates from the catalog, and actual cost from provider usage where available.

All amounts are the provider's price in USD. The platform fee is added on top.
"""

from typing import Any

from app.catalog.schema import ModelSpec

PLATFORM_FEE = 0.10


def _area_factor(size: Any) -> float:
    if not isinstance(size, str) or "x" not in size:
        return 1.0  # "auto": price as 1024x1024
    w, h = (int(x) for x in size.split("x"))
    return (w * h) / (1024 * 1024)


def estimate_cost(model: ModelSpec, params: dict[str, Any]) -> float:
    p = model.pricing
    rate = next(
        (r.usd for r in p.rates if all(params.get(k) in v for k, v in r.when.items())), None
    )
    if rate is None:
        raise ValueError(f"No price configured for {model.id} with {params}")
    cost = rate
    if p.quantity_param:
        cost *= int(params.get(p.quantity_param, 1))
    if p.unit == "second" and p.seconds_param:
        cost *= float(params[p.seconds_param])
    if p.area_param:
        cost *= _area_factor(params.get(p.area_param))
    return round(cost, 6)


def cost_from_usage(model: ModelSpec, usage: dict[str, int] | None) -> float | None:
    """Exact provider cost from token usage, for token-priced models."""
    rates = model.pricing.token_rates
    if not rates or not usage:
        return None
    total = sum(usage.get(k, 0) * rates.get(k, 0.0) for k in usage) / 1_000_000
    return round(total, 6)


def with_fee(provider_cost: float) -> float:
    return round(provider_cost * (1 + PLATFORM_FEE), 6)
