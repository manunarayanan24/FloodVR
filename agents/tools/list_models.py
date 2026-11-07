"""List every model id served on the NVIDIA endpoint, optionally filtered.

    python -m agents.tools.list_models
    python -m agents.tools.list_models nemotron vl guard
"""

from __future__ import annotations

import sys

from agents.llm import _nvidia_client


def main() -> int:
    needles = [a.lower() for a in sys.argv[1:]]
    ids = sorted(m.id for m in _nvidia_client().models.list().data)
    shown = [i for i in ids if not needles or any(n in i.lower() for n in needles)]
    for i in shown:
        print(i)
    print(f"\n{len(shown)} of {len(ids)} served models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
