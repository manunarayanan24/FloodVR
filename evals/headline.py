"""The two security numbers we report, side by side.

(a) detection miss rate on the freshest held-out set (rules never tuned on it), and
(b) end-to-end impact rate: share of those attacks that changed the claim's payout,
    peril, coverage or status (from evals/endtoend.json).

Both come from files written by the eval runners; nothing here is hand-typed.
`refresh()` merges them into evals/results.json and re-renders evals/report.html,
so /results and the report always show the pair together.
"""

from __future__ import annotations

import json
from typing import Any

from agents import settings

RESULTS_PATH = settings.EVALS_DIR / "results.json"
ENDTOEND_PATH = settings.EVALS_DIR / "endtoend.json"

# The set we report. Rules were tuned on "heldout"; "heldout2" was generated after.
# If a newer, untouched set is added, change this one constant.
REPORTED_SET = "heldout2"


def _load(path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build(results: dict[str, Any], endtoend: dict[str, Any] | None) -> dict[str, Any]:
    det = results.get("sets", {}).get(REPORTED_SET)
    head: dict[str, Any] = {"reported_set": REPORTED_SET}
    if det:
        head["detection"] = {
            "attacks": det["total"],
            "missed": det["missed"],
            "miss_rate": round(det["missed"] / det["total"], 4) if det["total"] else None,
        }
    if endtoend and endtoend.get("set") == REPORTED_SET:
        ours = endtoend["ours"]
        ad = ours.get("agentdojo", {})
        head["impact"] = {
            "attacks": ours["attacks"],
            "claims_changed_guard_on": ours["claim_changed_guard_on"],
            "claims_changed_guard_off": ours["claim_changed_guard_off"],
            "impact_rate_guard_on": ours["claim_change_rate_guard_on"],
            "impact_rate_guard_off": ours["claim_change_rate_guard_off"],
            "targeted_asr": ad.get("targeted_asr"),
            "utility_under_attack": ad.get("utility_under_attack"),
            "flow_violations": ad.get("flow_violations"),
            "live_intake": not ours.get("offline", True),
            "measured_at": endtoend.get("generated_at"),
        }
    elif endtoend:
        head["impact_note"] = (f"endtoend.json is for set {endtoend.get('set')!r}, "
                               f"not {REPORTED_SET!r}; run "
                               f"`python -m evals.endtoend --set {REPORTED_SET}`")
    head["pitch"] = _pitch(head)
    return head


def _pitch(head: dict[str, Any]) -> str:
    d, i = head.get("detection"), head.get("impact")
    if not (d and i):
        return ""
    return (f"Detection misses {d['missed']}/{d['attacks']} "
            f"({d['miss_rate'] * 100:.1f}%) of fresh attacks; "
            f"{i['claims_changed_guard_on']}/{i['attacks']} changed the claim "
            f"({i['impact_rate_guard_on'] * 100:.1f}%), even with the guard off "
            f"{i['claims_changed_guard_off']}/{i['attacks']}.")


def refresh() -> dict[str, Any] | None:
    results = _load(RESULTS_PATH)
    if not results:
        return None
    results["headline"] = build(results, _load(ENDTOEND_PATH))
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    from evals.report import write_report
    write_report(results)
    return results["headline"]


if __name__ == "__main__":
    h = refresh()
    print(json.dumps(h, indent=2) if h else "no evals/results.json — run python -m evals.run")
