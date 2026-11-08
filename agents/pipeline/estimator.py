"""Estimator — costs come from contracts/costs.json and nowhere else.

This is a capability limit, not a model. Even a fully hijacked pipeline cannot
emit an arbitrary payout, because no code path lets evidence text reach a price.
"""

from __future__ import annotations

from agents import settings
from agents.schemas import DamageItem, Estimate, SecurityFinding


def _type_for(item: DamageItem) -> str:
    table = settings.costs()
    mapped = table["item_type_map"].get(item.id)
    if mapped:
        return mapped
    return table["category_fallback"][item.category.value]


def estimate_for(item: DamageItem) -> tuple[Estimate, list[SecurityFinding]]:
    """Cost range for one item, clamped to the table. Returns any bounds finding."""
    table = settings.costs()
    entry = table["types"][_type_for(item)]
    mult = float(table["severity_multiplier"][str(item.severity)])

    low = float(entry["low_usd"]) * mult
    high = float(entry["high_usd"]) * mult

    per_unit = entry.get("per_unit")
    if per_unit and per_unit["unit"] == item.unit:
        low = max(low, float(per_unit["low"]) * item.measuredValue)
        high = max(high, float(per_unit["high"]) * item.measuredValue)

    geo = entry.get("per_geometry")
    if geo:
        q = quantity_for(item)
        if q:
            low = max(low, float(geo["low"]) * q["value"])
            high = max(high, float(geo["high"]) * q["value"])

    findings: list[SecurityFinding] = []
    cap = float(table["global_clamp"]["max_line_item_usd"])
    if high > cap:
        findings.append(SecurityFinding(
            source=f"manifest:{item.id}", channel="manifest_note",
            snippet=f"computed high ${high:,.0f} exceeds line-item cap ${cap:,.0f}",
            rule="BOUNDS_line_item_cap", layer="bounds", severity="medium",
            action_taken="stripped",
        ))
        high = cap
        low = min(low, cap)

    if low > high:
        low = high
    return Estimate(low_usd=round(low, 2), high_usd=round(high, 2)), findings


def quantity_for(item: DamageItem) -> dict | None:
    """Geometry quantity used for this item's price, if its type declares one."""
    geo = settings.costs()["types"][_type_for(item)].get("per_geometry")
    if not geo:
        return None
    from agents.pipeline import measure
    return measure.quantity(item.id, geo["quantity"])


def trade_for(item: DamageItem) -> str:
    table = settings.costs()
    return table["types"][_type_for(item)].get("trade", "none")
