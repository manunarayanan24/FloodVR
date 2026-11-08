"""Measurement tools: quantities from Mac 1's house_geometry.json, no LLM.

Recomputes every area from raw wall lengths and openings (rather than trusting
the exported totals), cross-checks against Mac 1's precomputed numbers, and
supplies geometry quantities to the estimator:

  flood_cut_m2      drywall removed to the flood-cut height (waterline + 0.6 m)
  wall_below_wl_m2  wall area below the waterline
  floor_m2          floor area
  baseboard_m       wall run at floor level, minus floor-level openings (doors, arches)

Which item uses which quantity is declared in contracts/costs.json
(`types.*.per_geometry`); which rooms an item covers is resolved from its id
suffix (`_living_room`, `_kitchen`, `_hallway`, `_closet`, `_all`). Quantities
are TRUSTED-structure data from Unity (numbers only, no free text).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from agents import settings

GEOMETRY = settings.CONTRACTS_DIR / "samples" / "house_geometry.json"

_ROOM_SUFFIX = {
    "living_room": ["living_room"],
    "kitchen": ["kitchen"],
    "hallway": ["hallway"],
    "closet": ["hallway_closet"],
}
ALL_ITEMS = {"waterline_band", "mud_floor_all"}


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _wall_area_below(wall: dict, h: float) -> float:
    gross = wall["length"]["m"] * min(h, wall["height"]["m"])
    holes = sum(o["width"]["m"] * _overlap(o["sill"]["m"], o["sill"]["m"] + o["height"]["m"], 0.0, h)
                for o in wall.get("openings", []))
    return max(0.0, gross - holes)


def _baseboard(wall: dict) -> float:
    floor_gaps = sum(o["width"]["m"] for o in wall.get("openings", []) if o["sill"]["m"] <= 0.01)
    return max(0.0, wall["length"]["m"] - floor_gaps)


@lru_cache(maxsize=1)
def rooms() -> dict[str, dict[str, Any]]:
    """Per-room quantities recomputed from walls, plus Mac 1's exported values."""
    if not GEOMETRY.exists():
        return {}
    g = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    wl, fc = g["waterlineHeight"]["m"], g["floodCutHeight"]["m"]
    out = {}
    for r in g["rooms"]:
        walls = r["walls"]
        q = {
            "floor_m2": r["floorArea"]["m2"],
            "wall_below_wl_m2": sum(_wall_area_below(w, wl) for w in walls),
            "flood_cut_m2": sum(_wall_area_below(w, fc) for w in walls),
            "baseboard_m": sum(_baseboard(w) for w in walls),
        }
        out[r["id"]] = {
            "label": r.get("label", r["id"]),
            **{k: round(v, 2) for k, v in q.items()},
            "exported": {"wall_below_wl_m2": r["wallAreaBelowWaterline"]["m2"],
                         "flood_cut_m2": r["floodCutDrywallArea"]["m2"]},
        }
    return out


def cross_check(tol: float = 0.05) -> dict[str, Any]:
    """Our recomputation vs Mac 1's exported totals."""
    rows, ok = [], True
    for rid, r in rooms().items():
        for k in ("wall_below_wl_m2", "flood_cut_m2"):
            diff = abs(r[k] - r["exported"][k])
            ok &= diff <= tol
            rows.append({"room": rid, "quantity": k, "ours": r[k],
                         "exported": round(r["exported"][k], 2), "match": diff <= tol})
    return {"all_match": ok, "rows": rows}


def rooms_for(item_id: str) -> list[str]:
    if item_id in ALL_ITEMS or item_id.endswith("_all"):
        return list(rooms())
    for suffix, rids in _ROOM_SUFFIX.items():
        if item_id.endswith("_" + suffix):
            return [r for r in rids if r in rooms()]
    return []


def quantity(item_id: str, kind: str) -> dict[str, Any] | None:
    rids = rooms_for(item_id)
    if not rids:
        return None
    rs = rooms()
    value = round(sum(rs[r][kind] for r in rids), 2)
    unit = "m" if kind.endswith("_m") else "m2"
    return {"value": value, "unit": unit, "kind": kind, "rooms": rids,
            "source": "contracts/samples/house_geometry.json"}


def summary() -> dict[str, Any]:
    rs = rooms()
    totals = {k: round(sum(r[k] for r in rs.values()), 2)
              for k in ("floor_m2", "wall_below_wl_m2", "flood_cut_m2", "baseboard_m")}
    return {"rooms": rs, "house_totals": totals, "cross_check": cross_check()}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    s = summary()
    for rid, r in s["rooms"].items():
        print(f"  {rid:<15} floor {r['floor_m2']:>6} m2  below-WL {r['wall_below_wl_m2']:>6} m2  "
              f"flood-cut {r['flood_cut_m2']:>6} m2  baseboard {r['baseboard_m']:>5} m")
    print(f"  {'HOUSE':<15} {s['house_totals']}")
    cc = s["cross_check"]
    print(f"  cross-check vs Mac 1 export: {'ALL MATCH' if cc['all_match'] else 'MISMATCH'}")
    for row in cc["rows"]:
        if not row["match"]:
            print(f"    {row}")
