"""Headset callouts (contracts/callouts.schema.json) from a finished ClaimDraft.

Short, fixed-template lines (<= 60 chars) the VR app renders as a coloured dot
plus text. Every `text` and `detail` is OUR template filled with numbers and
ids from structured data — never evidence text, never scene text, never a
finding snippet — so the headset cannot be used to replay an injection.

Positions come from the manifest (raised RAISE_M so a floor-level item's dot is
visible); scene-text callouts carry no position and the app anchors them on the
SceneText prop by id.
"""

from __future__ import annotations

from typing import Any

from agents import settings
from agents.schemas import ClaimDraft, DamageManifest, Peril

MAX_TEXT = 60
RAISE_M = 0.35

_HAZARD_TEXT = {
    "electrical": "Live outlet underwater - do not approach",
    "gas_co": "Submerged gas appliance - do not restart",
    "structural": "Structural crack - engineer before entry",
    "mold_airquality": "Mold growth - respirator, dry out in 48 h",
    "contamination": "Contaminated water - PPE required",
}
_HAZARD_COLOR = {"electrical": "red", "gas_co": "red", "structural": "red",
                 "mold_airquality": "amber", "contamination": "amber"}


def _room(item_id: str) -> str:
    for suffix, room in (("_living_room", "living_room"), ("_kitchen", "kitchen"),
                         ("_hallway", "hallway"), ("_closet", "closet")):
        if item_id.endswith(suffix):
            return room
    if item_id.endswith("_all") or item_id == "waterline_band":
        return "whole_house"
    return ""


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."


def _ft_in(m: float) -> str:
    inches = round(m / 0.0254)
    return f"{inches // 12} ft {inches % 12} in"


def build(draft: ClaimDraft, manifest: DamageManifest, seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen or set()
    items = {i.id: i for i in manifest.items}
    wl = settings.waterline_m()
    out: list[dict[str, Any]] = []

    def add(cid: str, item_id: str, kind: str, text: str, priority: int, color: str,
            detail: str = "", anchored: bool = True) -> None:
        if cid in seen or item_id in seen:
            return
        c: dict[str, Any] = {"id": cid, "item_id": item_id, "kind": kind,
                             "text": _clip(text, MAX_TEXT), "priority": priority, "color": color}
        it = items.get(item_id)
        if anchored and it is not None and it.position is not None:
            c["position"] = {"x": round(it.position.x, 3),
                             "y": round(max(it.position.y, 0.0) + RAISE_M, 3),
                             "z": round(it.position.z, 3)}
        room = _room(item_id)
        if room:
            c["room"] = room
        if detail:
            c["detail"] = _clip(detail, 300)
        out.append(c)

    # 1. Life-safety and other hazards.
    for h in draft.hazards:
        if h.priority > 3:
            continue
        add(f"hazard:{h.item_id}", h.item_id, "hazard",
            _HAZARD_TEXT.get(h.hazard_type, "Hazard - keep clear"), h.priority,
            _HAZARD_COLOR.get(h.hazard_type, "red"),
            f"{h.action} Dispatch: {h.dispatch.replace('_', ' ')}.")

    # 2. Injection attempts caught on text inside the house.
    blocked = sorted({f.source.split(":", 1)[1] for f in draft.security_findings
                      if f.source.startswith("scene_text:") and f.layer == "rules"})
    for sid in blocked:
        rules = sorted({f.rule for f in draft.security_findings if f.source == f"scene_text:{sid}"})
        add(f"blocked:{sid}", sid, "blocked", "Injection caught: this note tries to steer the AI",
            2, "amber",
            f"Text on this prop gives the AI instructions about the claim. It was blocked "
            f"before any agent read it ({len(rules)} rule(s) fired). It is not evidence.",
            anchored=False)

    # 3. Coverage determinations worth seeing in place.
    for li in draft.line_items:
        if li.peril is Peril.wind_driven_rain:
            add(f"coverage:{li.item_id}", li.item_id, "coverage",
                "Above waterline: wind-driven rain, not flood", 3, "blue",
                f"Excluded under the flood policy ({li.exclusion_ref or 'exclusion'}); routed to "
                f"the homeowners policy. Estimate ${li.estimate.low_usd:,.0f}-${li.estimate.high_usd:,.0f}.")

    # 4. Measurements.
    if "waterline_band" in items:
        add("measurement:waterline", "waterline_band", "measurement",
            f"Water reached {wl:.2f} m ({_ft_in(wl)})", 3, "blue",
            "Waterline height from house_geometry.json, visible on every wall.")
    fc = next((li for li in draft.line_items if li.item_id == "waterline_band" and li.quantity), None)
    if fc:
        add("measurement:flood_cut", "waterline_band", "measurement",
            f"Flood cut to 1.5 m: {fc.quantity['value']:.1f} m2 of drywall", 4, "blue",
            f"Recomputed from walls and openings in {len(fc.quantity['rooms'])} rooms. "
            f"Estimate ${fc.estimate.low_usd:,.0f}-${fc.estimate.high_usd:,.0f}.", anchored=False)

    # 5. Confirmed undamaged contents (the fraud-checker evidence).
    for it in manifest.items:
        if it.is_undamaged:
            add(f"undamaged:{it.id}", it.id, "measurement",
                f"{it.height_m:.2f} m up: above waterline, undamaged", 4, "green",
                "Recorded in the scene at severity 0. A claim that this item was destroyed "
                "will be flagged by the consistency checker.")

    # 6. Consistency findings from evidence in this run.
    for n, f in enumerate(x for x in draft.security_findings if x.layer == "consistency"):
        iid = next((i for i in items if f"'{i}'" in f.snippet), "")
        if not iid:
            continue
        add(f"consistency:{n}", iid, "coverage", "Claim conflicts with the scene - review", 2,
            "amber", f.rule.removeprefix("CONSISTENCY_").replace("_", " ") + ".")

    out.sort(key=lambda c: (c["priority"], c["id"]))
    return {"generated_at": draft.generated_at, "audit_trail_id": draft.audit_trail_id,
            "waterline_m": round(wl, 3), "callouts": out[:40]}
