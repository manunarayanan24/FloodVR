"""Print the attacks the guard missed, in full, grouped by technique.

    python -m agents.tools.show_misses [seed|heldout]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from agents import settings


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "heldout"
    results = json.loads((settings.EVALS_DIR / "results.json").read_text(encoding="utf-8"))
    missed = results["sets"][which]["missed_attacks"]

    src = settings.EVALS_DIR / "attacks" / (
        "generated_heldout.json" if which == "heldout" else "seed_attacks.json"
    )
    by_id = {a["id"]: a for a in json.loads(src.read_text(encoding="utf-8"))["attacks"]}

    groups: dict[str, list[dict]] = defaultdict(list)
    for m in missed:
        groups[m["technique"]].append(m)

    print(f"{len(missed)} missed in '{which}', {len(groups)} techniques\n")
    for tech, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"### {tech}  ({len(items)})")
        for m in items:
            full = by_id.get(m["id"], {})
            text = full.get("text", m.get("text", "")).replace("\n", " | ")
            print(f"  {m['id']} [{m['channel']}]")
            print(f"    {text[:320]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
