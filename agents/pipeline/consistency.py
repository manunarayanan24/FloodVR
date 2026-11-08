"""Consistency / Fraud Checker (agent 6): what the claim says vs what the scene shows.

Deterministic on purpose. It reads only the schema-validated `ExtractedEvidence`
(never raw text) plus Mac 1's manifest, and raises `SecurityFinding`s with
layer="consistency". It never edits a line item, a peril, a cost or the status:
a fraud signal is something the human adjuster weighs, not something an agent
acts on. (That also keeps the end-to-end eval honest: a finding is not a claim
change.)

Checks
1. claimed_undamaged — evidence claims an item the scene records at severity 0
   (present, confirmed undamaged). The planted trap: `laptop_undamaged` at
   1.6 m and `electronics_undamaged` at 1.45 m, both above the 0.9 m waterline.
2. above_waterline — evidence claims flood damage to a contents item whose
   measured height (heightAboveFloor, only trusted when non-zero) is above the
   waterline. Flood water cannot reach it.
3. padded_bid — a contractor estimate whose stated total exceeds our rate-table
   high for the items it covers by more than PADDING_RATIO. Our number comes
   from contracts/costs.json; theirs is only ever compared, never used.
4. total_loss_claim — evidence asserts "total loss" while most of the house's
   items are repairable per the manifest.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from agents import settings
from agents.schemas import Channel, SecurityFinding, TraceStep

if TYPE_CHECKING:
    from agents.pipeline.orchestrator import Run

PADDING_RATIO = 1.25


def _finding(source: str, rule: str, snippet: str, severity: str = "medium") -> SecurityFinding:
    return SecurityFinding(
        source=source, channel=Channel.homeowner_statement, snippet=snippet[:400],
        rule=f"CONSISTENCY_{rule}", layer="consistency", severity=severity,
        action_taken="flagged_only",
    )


def check(run: "Run") -> list[SecurityFinding]:
    items = {i.id: i for i in run.req.manifest.items}
    channel_of = {d.doc_id: d.channel for d in run.req.evidence}
    estimate_high = {li.item_id: li.estimate.high_usd for li in run.line_items}
    waterline = settings.waterline_m()
    out: list[SecurityFinding] = []

    for ev in run.extracted:
        src = f"evidence:{ev.doc_id}"
        for iid in ev.claimed_item_ids:
            it = items.get(iid)
            if it is None:
                continue
            if it.is_undamaged:
                out.append(_finding(
                    src, "claimed_undamaged",
                    f"claims '{iid}' but the scene records it present and undamaged "
                    f"(severity 0, {it.height_m:.2f} m above floor)", "high"))
            elif it.heightAboveFloor and it.heightAboveFloor > waterline \
                    and it.category.value in ("contents", "flood"):
                out.append(_finding(
                    src, "above_waterline",
                    f"claims flood damage to '{iid}' at {it.heightAboveFloor:.2f} m, "
                    f"above the {waterline:.2f} m waterline"))

        if channel_of.get(ev.doc_id) is Channel.contractor_estimate and ev.claimed_amounts_usd:
            bid = max(sum(ev.claimed_amounts_usd), max(ev.claimed_amounts_usd))
            covered = [i for i in ev.claimed_item_ids if i in estimate_high]
            ours = (sum(estimate_high[i] for i in covered) if covered
                    else sum(estimate_high.values()))
            scope = f"{len(covered)} item(s)" if covered else "the whole claim"
            if ours > 0 and bid > ours * PADDING_RATIO:
                out.append(_finding(
                    src, "padded_bid",
                    f"contractor total ${bid:,.0f} is {bid / ours:.1f}x our rate-table "
                    f"high ${ours:,.0f} for {scope}", "high"))

        if ev.mentions_total_loss:
            repairable = sum(1 for li in run.line_items if li.estimate.high_usd < 5000)
            if run.line_items and repairable / len(run.line_items) > 0.5:
                out.append(_finding(
                    src, "total_loss_claim",
                    f"asserts total loss, but {repairable}/{len(run.line_items)} "
                    f"line items are repairable under $5,000", "low"))
    return out


def run_stage(run: "Run") -> dict[str, Any]:
    """Stage entry used by Run.consistency() and the planner tool."""
    if "consistency" in run.done:
        return {"already_done": True}
    run._need("adjudicate")
    t0 = time.perf_counter()
    found = check(run)
    run.findings.extend(found)
    by_rule: dict[str, int] = {}
    for f in found:
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    run.trace.append(TraceStep(
        agent="consistency_checker", model="deterministic (manifest vs evidence)",
        ms=(time.perf_counter() - t0) * 1000, tool_calls=["get_manifest"],
        note=(f"{len(found)} inconsistency finding(s): "
              + ", ".join(f"{k.removeprefix('CONSISTENCY_')}={v}" for k, v in by_rule.items())
              if found else "no inconsistencies between evidence and scene"),
    ))
    run.done.append("consistency")
    return {"findings": len(found), "by_rule": {k.removeprefix("CONSISTENCY_"): v
                                                for k, v in by_rule.items()}}
