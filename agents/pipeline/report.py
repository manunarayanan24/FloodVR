"""Printable claim report data (GET /report/data, rendered by GET /report).

Built only from the finished, guarded ClaimDraft and the manifest. Every string
goes through output_guard.sanitise_text. Blocked injections are reported as
rule names and counts only: the injected text is never included.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from agents import output_guard
from agents.schemas import ClaimDraft, DamageManifest

_CLAUSE = re.compile(r"\b(?:[A-Z]{2}-[A-Z]{2,5}-\d+|ADJ-\d+)\b")
_UNIT = {"m2": "m²", "m": "m"}


def _s(x: Any, n: int = 2000) -> str:
    return output_guard.sanitise_text(str(x if x is not None else ""))[0][:n]


def _room_label(item, rooms: dict[str, dict]) -> str:
    from agents.voice.notes import _room_of
    rid = _room_of(item) if item is not None else None
    if rid is None:
        return "Whole house"
    return rooms.get(rid, {}).get("label", rid.replace("_", " ").title())


def build(draft: ClaimDraft, manifest: DamageManifest | None) -> dict[str, Any]:
    from agents.pipeline import measure
    rooms = measure.rooms()
    items = {i.id: i for i in (manifest.items if manifest else [])}
    t = draft.totals

    lines = []
    for li in draft.line_items:
        it = items.get(li.item_id)
        house_wide = len(measure.rooms_for(li.item_id)) > 1
        clauses = list(dict.fromkeys(([li.exclusion_ref] if li.exclusion_ref else [])
                                     + _CLAUSE.findall(li.rationale or "")))
        q = li.quantity or {}
        qty = (f"{q['value']:g} {_UNIT.get(q.get('unit'), q.get('unit', ''))} "
               f"{q.get('kind', '').replace('_m2', '').replace('_m', '').replace('_', ' ')}".strip()
               if q.get("value") else "")
        lines.append({
            "item": _s(li.label, 80),
            "room": _s("Whole house" if house_wide else _room_label(it, rooms), 40),
            "peril": _s(li.peril.value.replace("_", " "), 40),
            "policy": _s(li.coverage.value.replace("_", " "), 40),
            "clauses": [_s(c, 20) for c in clauses],
            "quantity": _s(qty, 60),
            "low": li.estimate.low_usd, "high": li.estimate.high_usd,
        })

    hazards = [{
        "priority": h.priority,
        "item": _s(items[h.item_id].label if h.item_id in items else h.item_id, 80),
        "type": _s(h.hazard_type.replace("gas_co", "gas / carbon monoxide").replace("_", " "), 40),
        "action": _s(h.action, 300),
        "dispatch": _s(h.dispatch.replace("_", " "), 40),
    } for h in sorted(draft.hazards, key=lambda h: (h.priority, h.item_id))]

    blocked = [f for f in draft.security_findings if f.action_taken == "blocked"]
    flagged = [f for f in draft.security_findings if f.action_taken != "blocked"]
    by_rule = Counter(f.rule for f in blocked)
    sources = {f.source.split(":", 1)[0] for f in blocked}

    review = [{
        "item": _s(items[n.item_id].label if n.item_id in items else n.item_id, 80),
        "reason": _s(n.reason, 300),
    } for n in draft.needs_human_review]

    fc = draft.flow_control or {}
    rep = draft.adjuster_report or {}
    return {
        "title": "Draft claim — pending adjuster approval",
        "status": _s(draft.status, 40),
        "generated_at": _s(draft.generated_at, 40),
        "audit_trail_id": _s(draft.audit_trail_id, 40),
        "totals": {"low": t.low_usd, "high": t.high_usd, "items": t.item_count,
                   "flood": list(t.flood_policy_usd), "homeowners": list(t.homeowners_policy_usd)},
        "report": {"text": _s(rep.get("text", ""), 6000), "source": _s(rep.get("source", ""), 20),
                   "numbers_checked": bool((rep.get("number_check") or {}).get("ok"))},
        "line_items": lines,
        "hazards": hazards,
        "flagged": [{"rule": _s(f.rule, 60), "layer": _s(f.layer, 20),
                     "source": _s(f.source.split(":", 1)[0].replace("_", " "), 40)} for f in flagged],
        "review": review,
        "blocked": {"total": len(blocked), "inputs": len({f.source for f in blocked}),
                    "channels": sorted(_s(x.replace("_", " "), 30) for x in sources),
                    "rules": [{"rule": _s(r, 60), "count": c} for r, c in by_rule.most_common()]},
        "flow": {"clean": bool(fc.get("clean")),
                 "statement": _s(fc.get("statement")
                                 or "No untrusted text reached a money decision.", 400),
                 "decision_fields_checked": fc.get("decision_fields_checked"),
                 "untrusted_inputs_seen": fc.get("untrusted_inputs_seen")},
    }
