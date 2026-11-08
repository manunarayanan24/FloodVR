"""Claim Writer (agent 4): Nemotron writes the adjuster report from structured facts.

Input is a facts dict built from the finished ClaimDraft: totals, per-item peril /
coverage / estimate, hazards, needs-human reasons, finding counts. No evidence
text, no claimant summary, no scene text — the writer never sees untrusted input.

Every number in the prose must appear in the facts. `check_numbers` extracts
each figure from the text and rejects any that is not a value present in the
facts (tolerance 0.5). On failure the writer gets one retry with the offending
numbers listed; if it still invents a figure, the report falls back to a
deterministic template. The prose is display only: it never feeds a decision.

The report then goes through the output guard (links, emails, HTML stripped)
and the same 6-word-shingle leakage check as decision fields.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from agents import output_guard, settings
from agents.schemas import ClaimDraft

_NUM = re.compile(r"(?<![A-Za-z_])\$?\d[\d,]*(?:\.\d+)?")

# Spelled-out numbers must not slip past the check ("twenty-four", "Six").
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_WORDNUM = re.compile(
    r"\b(?:(" + "|".join(_TENS) + r")(?:[- ](" + "|".join(list(_UNITS)[1:10]) + r"))?|("
    + "|".join(_UNITS) + r"))\b", re.IGNORECASE)


def _word_numbers(text: str) -> list[tuple[str, float]]:
    out = []
    for m in _WORDNUM.finditer(text):
        tens, unit, single = m.group(1), m.group(2), m.group(3)
        if single:
            if single.lower() == "one" and not re.search(r"priority[- ]one", m.string[max(0, m.start() - 9):m.end()], re.I):
                continue  # "one" is usually a pronoun ("the one in the kitchen")
            out.append((m.group(0), float(_UNITS[single.lower()])))
        else:
            out.append((m.group(0), float(_TENS[tens.lower()] + (_UNITS[unit.lower()] if unit else 0))))
    return out

_SYSTEM = """You write the claim summary an insurance adjuster reads first. You are given FACTS as JSON.

Rules:
- Use ONLY numbers that appear in FACTS, written in full (e.g. $22,855 — never "23k", never a rounded or computed figure, no percentages you calculated).
- Do not add totals, differences or counts that are not in FACTS.
- 170-260 words, plain prose, four short paragraphs IN THIS ORDER:
  1. Safety first: the priority-1 hazards and who must be dispatched.
  2. Scope and money: totals, then the line items that matter, each with its clause ids from FACTS (e.g. FL-COV-1, FL-EXCL-1); name any wind-driven-rain exclusion.
  3. Flagged findings: consistency findings (claims that conflict with the scene) and items needing human review.
  4. Blocked injections: which sources tried to instruct the system and were blocked before any agent read them (say how many rules fired; never quote them).
- When you name items needing human review, name exactly the items in needs_human with their reasons, no others.
- The claim is a draft pending the adjuster's decision. Never say it is approved or payable.
- No markdown headings, no links."""


_CLAUSE = re.compile(r"\b(?:[A-Z]{2}-[A-Z]{2,5}-\d+|ADJ-\d+)\b")


def facts(draft: ClaimDraft) -> dict[str, Any]:
    t = draft.totals
    layers: dict[str, int] = {}
    blocked: dict[str, int] = {}
    for f in draft.security_findings:
        layers[f.layer] = layers.get(f.layer, 0) + 1
        if f.layer in ("rules", "guard_model") and f.action_taken == "blocked":
            blocked[f.source] = blocked.get(f.source, 0) + 1
    return {
        "status": draft.status,
        "totals_usd": {"low": t.low_usd, "high": t.high_usd,
                       "flood_policy_low": t.flood_policy_usd[0],
                       "flood_policy_high": t.flood_policy_usd[1],
                       "homeowners_policy_low": t.homeowners_policy_usd[0],
                       "homeowners_policy_high": t.homeowners_policy_usd[1]},
        "line_item_count": t.item_count,
        "waterline_m": settings.waterline_m(),
        "line_items": [{"id": li.item_id, "label": li.label, "peril": li.peril.value,
                        "coverage": li.coverage.value, "exclusion": li.exclusion_ref,
                        "clauses": sorted(set(_CLAUSE.findall(li.rationale or ""))),
                        "low_usd": li.estimate.low_usd, "high_usd": li.estimate.high_usd}
                       for li in draft.line_items],
        "hazards": [{"id": h.item_id, "type": h.hazard_type, "priority": h.priority,
                     "dispatch": h.dispatch, "action": h.action} for h in draft.hazards],
        "priority_1_hazard_count": sum(1 for h in draft.hazards if h.priority == 1),
        "needs_human": [{"id": n.item_id, "reason": n.reason} for n in draft.needs_human_review],
        "needs_human_count": len(draft.needs_human_review),
        "flagged_findings": [{"rule": f.rule, "source": f.source} for f in draft.security_findings
                             if f.layer == "consistency"],
        "blocked_injections": [{"source": src, "rules_fired": n} for src, n in sorted(blocked.items())],
        "security_findings_by_layer": layers,
        "security_findings_count": len(draft.security_findings),
    }


def _values(obj: Any) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            v = _to_float(m.group(0))
            if v is not None:
                out.add(v)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out |= _values(k) | _values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _values(v)
    return out


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace("$", "").replace(",", "").rstrip("."))
    except ValueError:
        return None


def check_numbers(text: str, fact_dict: dict[str, Any]) -> dict[str, Any]:
    allowed = _values(fact_dict)
    found, unsupported = [], []
    for m in _NUM.finditer(text):
        raw = m.group(0).rstrip(".,")
        # skip digits glued to an id or a word like "priority-1" handled as 1
        v = _to_float(raw)
        if v is None:
            continue
        found.append(raw)
        if not any(abs(v - a) <= 0.5 for a in allowed):
            unsupported.append(raw)
    for raw, v in _word_numbers(text):
        found.append(raw)
        if not any(abs(v - a) <= 0.5 for a in allowed):
            unsupported.append(raw)
    return {"numbers_checked": len(found), "unsupported": unsupported,
            "ok": not unsupported}


def _template(f: dict[str, Any]) -> str:
    t = f["totals_usd"]
    p1 = [h for h in f["hazards"] if h["priority"] == 1]
    wdr = [li for li in f["line_items"] if li["peril"] == "wind_driven_rain"]
    big = sorted(f["line_items"], key=lambda li: -li["high_usd"])[:4]
    parts = [
        (f"{f['priority_1_hazard_count']} priority-1 hazards need dispatch before entry: "
         + "; ".join(f"{h['id']} ({h['dispatch']})" for h in p1) + "."
         if p1 else "No priority-1 hazards were found."),
        f"This draft covers {f['line_item_count']} damaged items with an estimated range of "
        f"${t['low']:,.0f} to ${t['high']:,.0f} (flood policy ${t['flood_policy_low']:,.0f} to "
        f"${t['flood_policy_high']:,.0f}; homeowners policy ${t['homeowners_policy_low']:,.0f} to "
        f"${t['homeowners_policy_high']:,.0f}). Largest lines: "
        + "; ".join(f"{li['id']} ${li['low_usd']:,.0f}-${li['high_usd']:,.0f} "
                    f"({', '.join(li['clauses']) or li['coverage']})" for li in big) + "."
        + ("".join(f" {li['id']} is wind-driven rain, excluded under {li['exclusion'] or 'the flood policy'} "
                   f"and routed to the homeowners policy." for li in wdr)),
        ((f"{len(f['flagged_findings'])} consistency findings: "
          + "; ".join(f"{x['rule'].removeprefix('CONSISTENCY_')} ({x['source']})" for x in f["flagged_findings"])
          + ". ") if f["flagged_findings"] else "No claim conflicts with the scene. ")
        + (f"{f['needs_human_count']} items need adjuster review: "
           + ", ".join(n["id"] for n in f["needs_human"]) + "." if f["needs_human"] else ""),
        ((f"Blocked injections: " + "; ".join(f"{b['source']} ({b['rules_fired']} rules fired)"
                                            for b in f["blocked_injections"]) + ". ")
         if f["blocked_injections"] else "No injection attempts were blocked. ")
        + "This is a draft pending the adjuster's decision.",
    ]
    return "\n\n".join(parts)


def write(draft: ClaimDraft, untrusted_texts: dict[str, str] | None = None) -> dict[str, Any]:
    f = facts(draft)
    t0 = time.perf_counter()
    text, model, source, attempts, check = "", "template", "template", 0, None

    if not settings.is_offline() and settings.has_key("nvidia"):
        from agents.llm import nvidia_chat
        user = "FACTS:\n" + json.dumps(f, indent=1)
        messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
        for attempts in (1, 2):
            try:
                comp = nvidia_chat("orchestrator", messages, max_tokens=1200, temperature=0.2,
                                   extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            except Exception:  # noqa: BLE001 - template below
                break
            cand = comp.text.strip()
            check = check_numbers(cand, f)
            if cand and check["ok"]:
                text, model, source = cand, comp.model, "llm"
                break
            messages += [{"role": "assistant", "content": cand},
                         {"role": "user", "content":
                          "These numbers are not in FACTS: " + ", ".join(check["unsupported"])
                          + ". Rewrite using only numbers from FACTS."}]

    rejected = None
    if source != "llm":
        rejected = check["unsupported"] if check and not check["ok"] else None
        text = _template(f)
        check = check_numbers(text, f)

    text, removed = output_guard.sanitise_text(text)
    leaked = False
    if untrusted_texts:
        from agents.taint import _shingles
        produced = _shingles(text)
        leaked = any(produced & _shingles(u) for u in untrusted_texts.values())
        if leaked:
            text, source = _template(f), "template"
    return {
        "text": text, "source": source, "model": model, "attempts": attempts,
        "ms": round((time.perf_counter() - t0) * 1000),
        "number_check": check, "llm_numbers_rejected": rejected,
        "output_guard_removed": removed, "untrusted_text_leaked": leaked,
    }
