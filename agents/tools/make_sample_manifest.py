"""Generate contracts/samples/house_manifest.json from Mac 1's Unity export.

Read-only on Assets/. Refuses to overwrite an existing sample unless --force is
passed, because Mac 1 owns that file and may push their own version.

    python -m agents.tools.make_sample_manifest [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "Assets" / "StreamingAssets" / "damage_manifest.json"
TARGET = REPO / "contracts" / "samples" / "house_manifest.json"

WATERLINE_M = 0.9


def infer_room(item: dict) -> str:
    """House is roughly 10 m (x) by 8 m (z). Derived from the Unity layout."""
    if item["id"] in {"mud_floor_all", "waterline_band"}:
        return "whole_house"
    pos = item.get("position")
    if not pos:
        return "whole_house"
    x, z = pos["x"], pos["z"]
    if z < 3.2:
        return "closet" if x < 1.6 else "hallway"
    return "kitchen" if x > 5.2 else "living_room"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not SOURCE.exists():
        print(f"ERROR: Unity export not found at {SOURCE}")
        print("Pull Mac 1's latest commit first.")
        return 1

    if TARGET.exists() and not args.force:
        print(f"SKIP: {TARGET.relative_to(REPO)} already exists (Mac 1 owns it).")
        print("Pass --force only if you are sure you should overwrite it.")
        return 0

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    items = []
    for raw in data["items"]:
        item = {
            "id": raw["id"],
            "label": raw["label"],
            "category": raw["category"],
            "severity": int(raw["severity"]),
            "measuredValue": round(float(raw["measuredValue"]), 3),
            "unit": raw["unit"],
            "note": raw["note"],
        }
        if "position" in raw:
            item["position"] = {k: round(float(v), 3) for k, v in raw["position"].items()}
        item["room"] = infer_room(raw)
        items.append(item)

    items.sort(key=lambda i: i["id"])
    payload = {
        "schema": "contracts/damage_manifest.schema.json",
        "source": "Assets/StreamingAssets/damage_manifest.json (Unity export, Mac 1)",
        "waterline_m": WATERLINE_M,
        "items": items,
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    above = [i["id"] for i in items if i.get("position", {}).get("y", 0) > WATERLINE_M]
    print(f"Wrote {TARGET.relative_to(REPO)}: {len(items)} items")
    print(f"Above the {WATERLINE_M} m waterline (wind-vs-water candidates): {above}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
