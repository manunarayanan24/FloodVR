"""Orchestrator — plans the run, merges agent output, writes the audit trail.

The privileged zone starts here. This function never sees raw untrusted text:
evidence arrives as `ExtractedEvidence`, which is schema-validated and bounded.
"""

from __future__ import annotations

import time

from agents import audit, guard, settings
from agents.pipeline import estimator, intake, peril, safety
from agents.schemas import (
    AssessRequest, Channel, ClaimDraft, Coverage, LineItem, SecurityFinding,
    TraceStep, Totals,
)


def _guard_text(
    text: str, source: str, channel: Channel, enabled: bool
) -> tuple[bool, list[SecurityFinding]]:
    if not enabled or not text.strip():
        return False, []
    return guard.inspect(text, source=source, channel=channel)


def assess(req: AssessRequest) -> ClaimDraft:
    run_id = audit.new_run_id()
    trace: list[TraceStep] = []
    findings: list[SecurityFinding] = []
    started_all = time.perf_counter()

    audit.append(run_id, "run_start", {
        "item_count": len(req.manifest.items),
        "evidence_count": len(req.evidence),
        "guard_enabled": req.guard_enabled,
        "offline": settings.is_offline(),
    })

    # ---- Guard pass over every untrusted surface -------------------------
    t0 = time.perf_counter()
    quarantined_docs: set[str] = set()

    for item in req.manifest.items:
        for field, value in (("note", item.note), ("label", item.label)):
            blocked, f = _guard_text(
                value, f"manifest:{item.id}.{field}", Channel.manifest_note,
                req.guard_enabled,
            )
            findings.extend(f)
            if blocked:
                # Strip the field rather than drop the damage record: the item is
                # real, only its free text is hostile.
                setattr(item, field, "[blocked: injected instruction removed]")

    for doc in req.evidence:
        blocked, f = _guard_text(doc.text, f"evidence:{doc.doc_id}", doc.channel,
                                 req.guard_enabled)
        findings.extend(f)
        if blocked:
            quarantined_docs.add(doc.doc_id)

    if req.adjuster_notes:
        blocked, f = _guard_text(req.adjuster_notes, "adjuster_notes",
                                 Channel.adjuster_notes, req.guard_enabled)
        findings.extend(f)

    for f in findings:
        f.action_taken = "blocked" if req.guard_enabled else "flagged_only"

    trace.append(TraceStep(
        agent="guard", model="rules+guard_model" if req.guard_enabled else "disabled",
        ms=(time.perf_counter() - t0) * 1000,
        note=f"{len(findings)} finding(s); {len(quarantined_docs)} document(s) quarantined",
    ))
    audit.append(run_id, "guard", {
        "findings": [f.model_dump(mode="json") for f in findings],
        "quarantined": sorted(quarantined_docs),
    })

    # ---- Intake (quarantined) -------------------------------------------
    t0 = time.perf_counter()
    known_ids = {i.id for i in req.manifest.items}
    extracted = []
    for doc in req.evidence:
        if doc.doc_id in quarantined_docs:
            continue  # blocked: never reaches the privileged zone at all
        extracted.append(intake.extract(doc, known_ids))

    trace.append(TraceStep(
        agent="intake", model=settings.model("intake")["id"],
        ms=(time.perf_counter() - t0) * 1000,
        note=f"{len(extracted)} document(s) extracted, "
             f"{len(quarantined_docs)} refused at the boundary",
    ))
    audit.append(run_id, "intake", {
        "extracted": [e.model_dump(mode="json") for e in extracted]
    })

    # ---- Peril / coverage + estimate -------------------------------------
    t0 = time.perf_counter()
    line_items: list[LineItem] = []
    needs_human = []
    evidence_by_item: dict[str, list[str]] = {}
    for ev in extracted:
        for item_id in ev.claimed_item_ids:
            evidence_by_item.setdefault(item_id, []).append(f"evidence:{ev.doc_id}")

    for item in req.manifest.items:
        p, cov, excl, conf, rationale = peril.adjudicate(item)
        est, bound_findings = estimator.estimate_for(item)
        findings.extend(bound_findings)

        refs = [f"manifest:{item.id}", *evidence_by_item.get(item.id, [])]
        line_items.append(LineItem(
            item_id=item.id, label=item.label, peril=p, coverage=cov,
            exclusion_ref=excl, estimate=est, confidence=conf,
            evidence_refs=refs, rationale=rationale,
        ))
        nh = peril.needs_human(item, p, cov)
        if nh:
            needs_human.append(nh)

    trace.append(TraceStep(
        agent="peril_coverage", model=settings.model("orchestrator")["id"],
        ms=(time.perf_counter() - t0) * 1000,
        tool_calls=["get_policy", "flag_for_human"],
        note=f"{sum(1 for li in line_items if li.peril.value == 'wind_driven_rain')} "
             f"wind-driven-rain determination(s)",
    ))

    t0 = time.perf_counter()
    hazards = safety.triage(req.manifest.items)
    trace.append(TraceStep(
        agent="safety_triage", model=settings.model("intake")["id"],
        ms=(time.perf_counter() - t0) * 1000,
        tool_calls=["get_hazard_rules"],
        note=f"{sum(1 for h in hazards if h.priority == 1)} priority-1 hazard(s)",
    ))

    # ---- Totals ----------------------------------------------------------
    flood = [li for li in line_items if li.coverage is Coverage.flood_policy]
    ho = [li for li in line_items if li.coverage is Coverage.homeowners_policy]
    totals = Totals(
        low_usd=round(sum(li.estimate.low_usd for li in line_items), 2),
        high_usd=round(sum(li.estimate.high_usd for li in line_items), 2),
        item_count=len(line_items),
        flood_policy_usd=(
            round(sum(li.estimate.low_usd for li in flood), 2),
            round(sum(li.estimate.high_usd for li in flood), 2),
        ),
        homeowners_policy_usd=(
            round(sum(li.estimate.low_usd for li in ho), 2),
            round(sum(li.estimate.high_usd for li in ho), 2),
        ),
    )

    cap = float(settings.costs()["global_clamp"]["max_claim_usd"])
    if totals.high_usd > cap:
        findings.append(SecurityFinding(
            source="totals", channel=Channel.manifest_note,
            snippet=f"claim total ${totals.high_usd:,.0f} exceeds cap ${cap:,.0f}",
            rule="BOUNDS_claim_cap", layer="bounds", severity="high",
            action_taken="flagged_only",
        ))

    draft = ClaimDraft(
        audit_trail_id=run_id, model_trace=trace, line_items=line_items,
        hazards=hazards, needs_human_review=needs_human, security_findings=findings,
        totals=totals,
    )

    audit.append(run_id, "claim_draft", {
        "totals": totals.model_dump(mode="json"),
        "line_item_count": len(line_items),
        "needs_human": len(needs_human),
        "elapsed_ms": round((time.perf_counter() - started_all) * 1000, 1),
    })
    return draft
