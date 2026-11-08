"""Score the Consistency / Fraud Checker on contracts/fixtures/consistency_cases.json.

Each case is one evidence document run through the full pipeline (fixed order).
A case passes when the CONSISTENCY_* findings it raises match `expect` exactly
(as a multiset). Also confirms the checker never changes the claim: totals,
perils and coverages must equal a run with no evidence.

    python -m evals.consistency            # uses live intake if FLOODVR_OFFLINE=0
    FLOODVR_OFFLINE=1 python -m evals.consistency
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from agents import settings
from agents.pipeline.orchestrator import assess
from agents.schemas import AssessRequest, DamageManifest

CASES = settings.CONTRACTS_DIR / "fixtures" / "consistency_cases.json"
MANIFEST = settings.CONTRACTS_DIR / "samples" / "house_manifest.json"
OUT = settings.EVALS_DIR / "consistency.json"


def _manifest() -> DamageManifest:
    return DamageManifest.model_validate(json.loads(MANIFEST.read_text(encoding="utf-8")))


def _fp(d) -> tuple:
    return (d.totals.model_dump_json(),
            tuple((li.item_id, li.peril.value, li.coverage.value) for li in d.line_items),
            d.status)


def main() -> int:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    base = _fp(assess(AssessRequest(manifest=_manifest())))
    rows, passed, claim_changed = [], 0, 0
    tp = fp = fn = 0
    for c in cases:
        d = assess(AssessRequest(manifest=_manifest(), evidence=[
            {"doc_id": c["id"], "channel": c["channel"], "text": c["text"]}]))
        got = Counter(f.rule for f in d.security_findings if f.layer == "consistency")
        want = Counter(c["expect"])
        ok = got == want
        passed += ok
        tp += sum((got & want).values())
        fp += sum((got - want).values())
        fn += sum((want - got).values())
        changed = _fp(d) != base
        claim_changed += changed
        rows.append({"id": c["id"], "ok": ok, "expected": sorted(want.elements()),
                     "got": sorted(got.elements()), "claim_changed": changed,
                     "snippets": [f.snippet for f in d.security_findings
                                  if f.layer == "consistency"]})
        print(f"  {'PASS' if ok else 'FAIL'}  {c['id']:<28} got {sorted(got.elements()) or '-'}"
              + ("  CLAIM CHANGED" if changed else ""))
    res = {"offline": settings.is_offline(), "cases": len(cases), "passed": passed,
           "precision": round(tp / (tp + fp), 4) if tp + fp else None,
           "recall": round(tp / (tp + fn), 4) if tp + fn else None,
           "claim_changed_by_checker": claim_changed, "rows": rows}
    print(f"\nCONSISTENCY CHECKER  {passed}/{len(cases)} cases, precision {res['precision']}, "
          f"recall {res['recall']}, claims changed by checker {claim_changed} "
          f"({'offline regex intake' if res['offline'] else 'live LLM intake'})")
    OUT.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
