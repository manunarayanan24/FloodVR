"""Orchestrator — plans the run, merges agent output, writes the audit trail.

The privileged zone starts here. This code never sees raw untrusted text:
evidence arrives as `ExtractedEvidence`, which is schema-validated and bounded.

The run is split into stages on `Run` (guard -> intake -> adjudicate ->
consistency -> triage -> finalize). `assess()` runs them in the fixed order. `agents.pipeline.planner`
lets Nemotron choose the order with tool calls; `Run` enforces the
preconditions either way (intake refuses before the guard, finalize runs any
required stage the planner skipped), so the LLM decides sequencing, never
peril, coverage, money or status.
"""

from __future__ import annotations

import time

from agents import audit, guard, output_guard, settings
from agents.pipeline import estimator, intake, peril, safety
from agents.schemas import (
    AssessRequest, Channel, ClaimDraft, Coverage, Estimate, LineItem, SecurityFinding,
    TraceStep, Totals, TrustLabel,
)
from agents.taint import Ledger
from agents.trust import CHANNEL_TRUST, new_canary  # noqa: F401 - re-exported


def _guard_text(
    text: str, source: str, channel: Channel, enabled: bool
) -> tuple[bool, list[SecurityFinding]]:
    if not enabled or not text.strip():
        return False, []
    return guard.inspect(text, source=source, channel=channel)


class StageOrderError(RuntimeError):
    """A stage was called before the stage it depends on."""


REQUIRED_STAGES = ("guard", "intake", "vision", "measure", "peril", "price", "consistency", "triage")


class Run:
    def __init__(self, req: AssessRequest):
        self.req = req
        self.run_id = audit.new_run_id()
        self.trace: list[TraceStep] = []
        self.findings: list[SecurityFinding] = []
        self.started_all = time.perf_counter()
        self.ledger = Ledger()
        self.canary = new_canary(settings.config()["guard"]["canary_prefix"])
        self.done: list[str] = []
        self.enforced: list[str] = []
        self.quarantined_docs: set[str] = set()
        self.blocked_scene_text: set[str] = set()
        self.extracted: list = []
        self.line_items: list[LineItem] = []
        self.needs_human: list = []
        self.undamaged: list[str] = []
        self.hazards: list = []
        self.extra_findings_hooks: list = []
        self.draft: ClaimDraft | None = None

        # Every untrusted input is remembered so the flow check can verify, at the
        # end, that none of its text reached a decision. This is the empirical half
        # of the IFC claim: declarations can lie, a substring check cannot.
        for st in req.manifest.scene_text:
            self.ledger.record_untrusted(f"scene_text:{st.id}", st.text)
        for doc in req.evidence:
            self.ledger.record_untrusted(f"evidence:{doc.doc_id}", doc.text)
        if req.adjuster_notes:
            self.ledger.record_untrusted("adjuster_notes", req.adjuster_notes)

        audit.append(self.run_id, "run_start", {
            "item_count": len(req.manifest.items),
            "evidence_count": len(req.evidence),
            "guard_enabled": req.guard_enabled,
            "offline": settings.is_offline(),
        })

    def _need(self, *stages: str) -> None:
        missing = [s for s in stages if s not in self.done]
        if missing:
            raise StageOrderError(f"requires {', '.join(missing)} first")

    # ---- Guard pass over every untrusted surface -------------------------
    def guard(self) -> dict:
        if "guard" in self.done:
            return {"already_done": True}
        req, findings = self.req, self.findings
        t0 = time.perf_counter()
        start = len(findings)

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

        # scene_text is text painted inside the house (the fridge sticky note). It is
        # the demo's primary injection channel and is never trusted.
        for st in req.manifest.scene_text:
            blocked, f = _guard_text(
                st.text, f"scene_text:{st.id}", Channel.scene_text, req.guard_enabled
            )
            findings.extend(f)
            if blocked:
                self.blocked_scene_text.add(st.id)

        for doc in req.evidence:
            blocked, f = _guard_text(doc.text, f"evidence:{doc.doc_id}", doc.channel,
                                     req.guard_enabled)
            findings.extend(f)
            if blocked:
                self.quarantined_docs.add(doc.doc_id)

        if req.adjuster_notes:
            blocked, f = _guard_text(req.adjuster_notes, "adjuster_notes",
                                     Channel.adjuster_notes, req.guard_enabled)
            findings.extend(f)

        for f in findings[start:]:
            f.action_taken = "blocked" if req.guard_enabled else "flagged_only"

        n = len(findings) - start
        self.trace.append(TraceStep(
            agent="guard", model="rules+guard_model" if req.guard_enabled else "disabled",
            ms=(time.perf_counter() - t0) * 1000,
            note=f"{n} finding(s); {len(self.quarantined_docs)} document(s) and "
                 f"{len(self.blocked_scene_text)} scene-text item(s) quarantined",
        ))
        audit.append(self.run_id, "guard", {
            "findings": [f.model_dump(mode="json") for f in findings[start:]],
            "quarantined": sorted(self.quarantined_docs),
            "blocked_scene_text": sorted(self.blocked_scene_text),
        })
        self.done.append("guard")
        # Counts and flags only: this dict is what the planner LLM sees.
        return {"findings": n, "documents_quarantined": len(self.quarantined_docs),
                "scene_text_blocked": len(self.blocked_scene_text),
                "guard_enabled": req.guard_enabled}

    # ---- Intake (quarantined) -------------------------------------------
    def intake(self) -> dict:
        if "intake" in self.done:
            return {"already_done": True}
        self._need("guard")
        req = self.req
        t0 = time.perf_counter()
        known_ids = {i.id for i in req.manifest.items}
        for doc in req.evidence:
            if doc.doc_id in self.quarantined_docs:
                continue  # blocked: never reaches the privileged zone at all
            self.extracted.append(intake.extract(doc, known_ids))

        self.trace.append(TraceStep(
            agent="intake", model=settings.model("intake")["id"],
            ms=(time.perf_counter() - t0) * 1000,
            note=f"{len(self.extracted)} document(s) extracted, "
                 f"{len(self.quarantined_docs)} refused at the boundary",
        ))
        audit.append(self.run_id, "intake", {
            "extracted": [e.model_dump(mode="json") for e in self.extracted]
        })
        self.done.append("intake")
        return {"documents_extracted": len(self.extracted),
                "documents_refused": len(self.quarantined_docs)}

    # ---- Measurement tools (deterministic geometry) ----------------------
    def measure(self) -> dict:
        """Quantities from house_geometry.json, with the arithmetic in the trace."""
        if "measure" in self.done:
            return {"already_done": True}
        from agents.pipeline import measure
        t0 = time.perf_counter()
        rooms = measure.rooms()
        lines = []
        for rid, r in rooms.items():
            lines.append(f"{rid}: flood cut {r['math']['flood_cut_m2']}; "
                         f"baseboard {r['math']['baseboard_m']}; {r['math']['floor_m2']}")
        priced = [x for x in (estimator.explain(i) for i in self.req.manifest.items
                              if not i.is_undamaged) if x]
        cc = measure.cross_check()
        self.trace.append(TraceStep(
            agent="measurement_tools", model="deterministic (house_geometry.json)",
            ms=(time.perf_counter() - t0) * 1000,
            tool_calls=["flood_cut_area", "floor_area", "baseboard_length"],
            note=(" | ".join(lines + priced)
                  + f" | cross-check vs Unity export: {'all match' if cc['all_match'] else 'MISMATCH'}"),
        ))
        self.done.append("measure")
        tot = measure.summary()["house_totals"]
        return {"rooms": len(rooms), "flood_cut_m2": tot["flood_cut_m2"],
                "floor_m2": tot["floor_m2"], "baseboard_m": tot["baseboard_m"],
                "priced_by_quantity": len(priced), "cross_check_ok": cc["all_match"]}

    # ---- Peril / coverage + estimate -------------------------------------
    def peril(self) -> dict:
        """Peril / coverage per damaged item from contracts/policy.json (deterministic).
        Line items are created here with a zero estimate that price() fills in."""
        if "peril" in self.done:
            return {"already_done": True}
        self._need("intake")
        req, ledger = self.req, self.ledger
        t0 = time.perf_counter()
        evidence_by_item: dict[str, list[str]] = {}
        for ev in self.extracted:
            for item_id in ev.claimed_item_ids:
                evidence_by_item.setdefault(item_id, []).append(f"evidence:{ev.doc_id}")

        for item in req.manifest.items:
            if item.is_undamaged:
                # Severity 0: present but undamaged. Not claimable, and kept aside as
                # evidence for the consistency/fraud checker.
                self.undamaged.append(item.id)
                continue

            p, cov, excl, conf, rationale = peril.adjudicate(item)

            # Declare what fed this decision. Peril comes from the manifest item
            # (machine-generated) and the policy file (ours). Evidence feeds NEITHER:
            # it only ever lands in evidence_refs, which is display metadata.
            for fld in ("peril", "coverage", "rationale", "confidence"):
                ledger.record(f"line_items.{item.id}.{fld}",
                              f"manifest:{item.id}", TrustLabel.machine)
                ledger.record(f"line_items.{item.id}.{fld}",
                              "contracts/policy.json", TrustLabel.trusted)

            refs = [f"manifest:{item.id}", *evidence_by_item.get(item.id, [])]
            self.line_items.append(LineItem(
                item_id=item.id, label=item.label, peril=p, coverage=cov,
                exclusion_ref=excl, estimate=Estimate(low_usd=0.0, high_usd=0.0),
                confidence=conf, evidence_refs=refs, rationale=rationale,
            ))
            nh = peril.needs_human(item, p, cov)
            if nh:
                self.needs_human.append(nh)

        wdr = sum(1 for li in self.line_items if li.peril.value == "wind_driven_rain")
        self.trace.append(TraceStep(
            agent="peril_coverage", model="deterministic (contracts/policy.json)",
            ms=(time.perf_counter() - t0) * 1000,
            tool_calls=["get_policy", "flag_for_human"],
            note=f"{wdr} wind-driven-rain determination(s); {len(self.undamaged)} "
                 f"severity-0 item(s) excluded as undamaged",
        ))
        self.done.append("peril")
        return {"line_items": len(self.line_items), "wind_driven_rain": wdr,
                "needs_human": len(self.needs_human), "undamaged": len(self.undamaged)}

    def price(self) -> dict:
        """Estimates: contracts/costs.json x measured quantity, clamped (deterministic)."""
        if "price" in self.done:
            return {"already_done": True}
        self._need("peril", "measure")
        ledger = self.ledger
        t0 = time.perf_counter()
        items = {i.id: i for i in self.req.manifest.items}
        clamped = 0
        for li in self.line_items:
            item = items[li.item_id]
            est, bound_findings = estimator.estimate_for(item)
            qty = estimator.quantity_for(item)
            self.findings.extend(bound_findings)
            clamped += bool(bound_findings)
            ledger.record(f"line_items.{item.id}.estimate",
                          "contracts/costs.json", TrustLabel.trusted)
            ledger.record(f"line_items.{item.id}.estimate",
                          f"manifest:{item.id}", TrustLabel.machine)
            if qty:
                ledger.record(f"line_items.{item.id}.estimate",
                              "contracts/samples/house_geometry.json", TrustLabel.machine)
            li.estimate = est
            li.quantity = qty
        low = sum(li.estimate.low_usd for li in self.line_items)
        high = sum(li.estimate.high_usd for li in self.line_items)
        self.trace.append(TraceStep(
            agent="pricing", model="deterministic (contracts/costs.json)",
            ms=(time.perf_counter() - t0) * 1000, tool_calls=["lookup_cost"],
            note=f"{len(self.line_items)} line(s) priced, "
                 f"{sum(1 for li in self.line_items if li.quantity)} by measured quantity, "
                 f"{clamped} clamped; ${low:,.2f}-${high:,.2f}",
        ))
        self.done.append("price")
        return {"priced": len(self.line_items), "clamped": clamped,
                "by_quantity": sum(1 for li in self.line_items if li.quantity)}

    def adjudicate(self) -> dict:
        """peril() then price(), for callers that want both in one step."""
        self.peril()
        if "measure" not in self.done:
            self.measure()
        return self.price()

    def vision(self) -> dict:
        """Vision Inspector result for this house (cached Nemotron VL run, no LLM call
        here). Its transcriptions are UNTRUSTED: registered with the flow ledger so
        the end-of-run check proves none reached a decision, and guarded again."""
        if "vision" in self.done:
            return {"already_done": True}
        from agents.pipeline.vision import cached
        t0 = time.perf_counter()
        v = cached()
        if not v:
            self.trace.append(TraceStep(agent="vision_inspector", model="none",
                                        ms=0.0, note="no vision run cached"))
            self.done.append("vision")
            return {"available": False}
        flagged_frames = 0
        for img in v["images"]:
            text = " ".join(img.get("transcribed_text", []))
            if not text.strip():
                continue
            self.ledger.record_untrusted(f"vlm:{img['filename']}", text)
            blocked, f = _guard_text(text, f"vision:{img['filename']}", Channel.vlm_output,
                                     self.req.guard_enabled)
            for x in f:
                x.action_taken = "blocked" if self.req.guard_enabled else "flagged_only"
            self.findings.extend(f)
            flagged_frames += bool(f)
        s = v["summary"]
        d = s["detections_overall"]
        truth = d["true_positive"] + len(d["missed"])
        self.trace.append(TraceStep(
            agent="vision_inspector", model=next((i["model"] for i in v["images"] if i.get("model")), "vlm"),
            ms=(time.perf_counter() - t0) * 1000, tool_calls=["vision_read"],
            note=(f"found {d['true_positive']} of {truth} visible damage detections across "
                  f"{s['images']} frames ({d['false_positive']} extra), unique items "
                  f"{s['unique_items_found']}; scene text flagged in {flagged_frames}/"
                  f"{s['scene_text_images']} fridge frames. Upper bound: low-poly render. "
                  f"Feeds no decision. Cached run {v['generated_at'][:16]}"),
        ))
        self.done.append("vision")
        return {"available": True, "frames": s["images"], "found": d["true_positive"],
                "of": truth, "extra": d["false_positive"], "text_flagged_frames": flagged_frames}

    def consistency(self) -> dict:
        """Fraud checker: evidence vs scene. Findings only; never edits the claim."""
        from agents.pipeline import consistency
        return consistency.run_stage(self)

    def triage(self) -> dict:
        if "triage" in self.done:
            return {"already_done": True}
        t0 = time.perf_counter()
        self.hazards = safety.triage(self.req.manifest.items)
        p1 = sum(1 for h in self.hazards if h.priority == 1)
        self.trace.append(TraceStep(
            agent="safety_triage", model="deterministic (hazard rules)",
            ms=(time.perf_counter() - t0) * 1000,
            tool_calls=["get_hazard_rules"],
            note=f"{p1} priority-1 hazard(s)",
        ))
        self.done.append("triage")
        return {"hazards": len(self.hazards), "priority_1": p1}

    # ---- Totals, output guard, flow check --------------------------------
    def finalize(self) -> ClaimDraft:
        if self.draft is not None:
            return self.draft
        # Required stages a planner skipped are run here, in safe order.
        for stage in REQUIRED_STAGES:
            if stage not in self.done:
                self.enforced.append(stage)
                getattr(self, stage)()
        line_items, findings, ledger = self.line_items, self.findings, self.ledger

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

        for h in self.hazards:
            ledger.record(f"hazards.{h.item_id}.action",
                          f"manifest:{h.item_id}", TrustLabel.machine)

        draft = ClaimDraft(
            audit_trail_id=self.run_id, model_trace=self.trace, line_items=line_items,
            hazards=self.hazards, needs_human_review=self.needs_human,
            security_findings=findings, totals=totals,
        )

        # ---- Output-side guard --------------------------------------------
        # Google's layered defence re-scans the response, not just the input:
        # redact links and embeds, check the canary, re-run the rules on what we
        # are about to return.
        t0 = time.perf_counter()
        draft = output_guard.scrub(draft, canary=self.canary)
        out_findings = sum(1 for f in draft.security_findings if f.layer == "output")

        # ---- Information-flow check ----------------------------------------
        ledger.check_declarations()
        ledger.check_text_leakage(output_guard.decision_blob(draft))
        draft.flow_control = ledger.summary()
        for v in ledger.violations:
            draft.security_findings.append(SecurityFinding(
                source=v.source, channel=Channel.vlm_output,
                snippet=v.detail[:400], rule="FLOW_untrusted_reached_decision",
                layer="flow_control", severity="critical", action_taken="flagged_only",
            ))

        draft.model_trace.append(TraceStep(
            agent="output_guard+flow_control", model="deterministic",
            ms=(time.perf_counter() - t0) * 1000,
            note=f"{out_findings} output finding(s); flow "
                 f"{'CLEAN' if ledger.clean else 'VIOLATED'} across "
                 f"{len(ledger.entries)} decision fields vs "
                 f"{len(ledger.untrusted_texts)} untrusted input(s)",
        ))

        audit.append(self.run_id, "flow_control", ledger.summary())
        audit.append(self.run_id, "claim_draft", {
            "totals": totals.model_dump(mode="json"),
            "line_item_count": len(line_items),
            "needs_human": len(self.needs_human),
            "elapsed_ms": round((time.perf_counter() - self.started_all) * 1000, 1),
        })
        self.done.append("finalize")
        self.draft = draft
        return draft


def assess(req: AssessRequest) -> ClaimDraft:
    """Fixed-order run: offline default, eval baseline, and the planner's fallback."""
    run = Run(req)
    run.guard()
    run.intake()
    run.vision()
    run.measure()
    run.peril()
    run.price()
    run.consistency()
    run.triage()
    return run.finalize()
