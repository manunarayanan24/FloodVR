"""Safety / triage — ranks hazards and says who to dispatch.

Priority 1 means "before anyone re-enters the building".
"""

from __future__ import annotations

from agents.schemas import Category, DamageItem, Hazard

_ELECTRICAL = ("outlet", "electrical", "circuit", "energize", "energise", "shock")
_GAS = ("furnace", "gas", "combustion", "co ", "carbon monoxide")
_MOLD = ("mold", "mould", "air quality", "spore")
_WATER_HEATER = ("water heater",)


def _classify(item: DamageItem) -> tuple[str, str] | None:
    """Return (hazard_type, dispatch) or None if the item is not a hazard."""
    blob = f"{item.label} {item.note}".lower()

    if item.category is Category.structural:
        return "structural", "structural_engineer"
    # Mold is checked first: its notes legitimately mention the submerged
    # appliance that caused it, which would otherwise match the electrical and
    # gas keywords and dispatch the wrong trade.
    if any(k in blob for k in _MOLD):
        return "mold_airquality", "remediation_contractor"
    if any(k in blob for k in _GAS):
        return "gas_co", "gas_utility"
    if any(k in blob for k in _ELECTRICAL) or any(k in blob for k in _WATER_HEATER):
        return "electrical", "licensed_electrician"
    if item.category is Category.hazard:
        return "contamination", "remediation_contractor"
    return None


def triage(items: list[DamageItem]) -> list[Hazard]:
    hazards: list[Hazard] = []
    for item in items:
        classified = _classify(item)
        if not classified:
            continue
        hazard_type, dispatch = classified

        # Severity 5 life-safety items go to priority 1; 4 to priority 2.
        priority = {5: 1, 4: 2, 3: 3, 2: 4, 1: 5}[item.severity]
        if hazard_type in {"electrical", "gas_co"} and item.severity >= 4:
            priority = 1

        action = {
            "electrical": "Do not energise the circuit. Licensed electrician must "
                          "inspect and replace submerged components before power is restored.",
            "gas_co": "Do not operate. CO and fire risk. Gas utility must disconnect "
                      "and inspect before any attempt to restart.",
            "mold_airquality": "Contain and remediate. Negative-air containment and "
                               "air scrubbing before occupancy.",
            "structural": "Do not clear for re-occupancy. Structural engineer "
                          "assessment required before repair scope is set.",
            "contamination": "Treat as contaminated floodwater exposure. PPE required "
                             "for anyone entering.",
        }[hazard_type]

        hazards.append(Hazard(
            item_id=item.id, hazard_type=hazard_type, priority=priority,
            action=action, dispatch=dispatch,
        ))

    hazards.sort(key=lambda h: (h.priority, h.item_id))
    return hazards
