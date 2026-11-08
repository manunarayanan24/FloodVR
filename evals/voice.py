"""Score the Voice Notes agent on evals/voice_questions.json (a DEV set).

    python -m evals.voice            # live classifier (Nemotron Lightning) if a key is set
    FLOODVR_OFFLINE=1 python -m evals.voice   # regex classifier

Runs the guarded fixed-order assessment on the sample manifest once, then asks
every question against that draft, the way the headset does. Writes evals/voice.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agents import settings
from agents.pipeline.orchestrator import assess
from agents.schemas import AssessRequest
from agents.voice import notes

ROOT = Path(__file__).resolve().parent
QUESTIONS = ROOT / "voice_questions.json"
OUT = ROOT / "voice.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    manifest = json.loads((settings.CONTRACTS_DIR / "samples" / "house_manifest.json")
                          .read_text(encoding="utf-8"))
    req = AssessRequest.model_validate({"manifest": manifest, "evidence": [], "guard_enabled": True})
    draft = assess(req)
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    rows, ok_n = [], 0
    for q in qs:
        notes.SEEN.clear()
        notes.SEEN.update(q.get("seen", []))
        r = notes.handle(q["text"], gaze_item_id=q.get("gaze"), draft=draft, manifest=req.manifest)
        reply = r["spoken_reply"]
        low = reply.lower()
        ok = all(any(alt.lower() in low for alt in group) for group in q["expect"])
        ok_n += ok
        rows.append({"id": q["id"], "question": q["text"], "reply": reply, "ok": ok,
                     "classifier": r.get("classifier")})
        print(f"{'PASS' if ok else 'FAIL'}  {q['text']}\n      -> {reply}")
    notes.SEEN.clear()
    print(f"\n{ok_n}/{len(qs)} specific, correct answers "
          f"({'offline regex' if settings.is_offline() else 'live'} classifier)")
    OUT.write_text(json.dumps({"passed": ok_n, "total": len(qs), "offline": settings.is_offline(),
                               "rows": rows}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
