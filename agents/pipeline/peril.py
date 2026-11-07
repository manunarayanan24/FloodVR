"""Peril / coverage adjudication — the wind-vs-water agent.

Deterministic, driven by contracts/policy.json. This is on purpose: coverage
determinations must be reproducible and citable, and a model that can be talked
into a different peril is exactly the vulnerability we are demonstrating.
"""

from __future__ import annotations

from agents import settings
from agents.schemas import Category, Coverage, DamageItem, NeedsHuman, Peril

# Phrases in a manifest note that indicate entry ABOVE the waterline.
_WIND_EVIDENCE = ("wind-driven", "wind driven", "roof", "window", "above the flood",
                  "above the waterline", "rain intrusion")


def adjudicate(item: DamageItem) -> tuple[Peril, Coverage, str | None, float, str]:
    """Return (peril, coverage, exclusion_ref, confidence, rationale)."""
    waterline = settings.waterline_m()
    height = item.height_m
    note = (item.note or "").lower()
    above = height > waterline
    wind_evidence = any(k in note for k in _WIND_EVIDENCE)

    if item.category is Category.structural:
        return (
            Peril.structural, Coverage.needs_human, None, 0.55,
            f"ADJ-3: structural damage requires a licensed engineer assessment "
            f"before coverage is finalised.",
        )

    if item.category is Category.wind or (above and wind_evidence):
        return (
            Peril.wind_driven_rain, Coverage.homeowners_policy, "FL-EXCL-1", 0.72,
            f"ADJ-2: damage sits at {height:.2f} m, above the {waterline:.2f} m "
            f"waterline, and the evidence points to roof/window entry. Wind-driven "
            f"rain is covered under HO-COV-1 and excluded from the flood policy by "
            f"FL-EXCL-1. Contested peril — routed for human confirmation.",
        )

    if above and not wind_evidence:
        # Above the line but caused by what happened below it (e.g. mold on a wall
        # above a submerged water heater). Covered, but say why.
        return (
            Peril.flood, Coverage.flood_policy, None, 0.6,
            f"ADJ-1/FL-COV-3: at {height:.2f} m this sits above the waterline, but "
            f"the cause of loss is prolonged saturation from floodwater below it.",
        )

    if item.category is Category.contents:
        return (
            Peril.flood, Coverage.flood_policy, None, 0.8,
            "ADJ-1: contents damaged by inundation. Covered under the flood policy "
            "only with a contents endorsement (FL-EXCL-2) — otherwise HO-COV-2.",
        )

    if item.category is Category.hazard:
        return (
            Peril.flood, Coverage.flood_policy, None, 0.88,
            f"ADJ-1/FL-COV-2: building system submerged at {height:.2f} m, at or "
            f"below the {waterline:.2f} m waterline. Includes licensed inspection.",
        )

    return (
        Peril.flood, Coverage.flood_policy, None, 0.9,
        f"ADJ-1/FL-COV-1: damage at {height:.2f} m is at or below the "
        f"{waterline:.2f} m waterline and is direct physical loss from inundation.",
    )


def needs_human(item: DamageItem, peril: Peril, coverage: Coverage) -> NeedsHuman | None:
    if coverage is Coverage.needs_human:
        return NeedsHuman(item_id=item.id, reason="Structural assessment required (ADJ-3).")
    if peril is Peril.wind_driven_rain:
        return NeedsHuman(
            item_id=item.id,
            reason="Contested wind-vs-water determination (ADJ-2). Two policies are "
                   "in play; a human adjuster confirms which one pays.",
        )
    if item.severity >= 5:
        return NeedsHuman(
            item_id=item.id,
            reason="Severity 5 life-safety item. Human confirms before re-entry is cleared.",
        )
    return None
