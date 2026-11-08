"""Output-side guard.

Google's layered defence re-scans the *response*, not just the input: it
redacts suspicious URLs (including ones the model was talked into generating),
refuses to render external images, and runs a second reasoning pass before the
answer reaches the user. We scanned everything going in and nothing coming out,
which left the adjuster console rendering attacker-controlled text.

Three jobs here:
  1. Redact links and image embeds from anything we return.
  2. Check the canary never appears in output (prompt leak).
  3. Re-run the rule layer over the rendered draft and record findings.
"""

from __future__ import annotations

import re

from agents import guard
from agents.schemas import Channel, ClaimDraft, SecurityFinding

_URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"')\]]{2,}", re.IGNORECASE)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML_TAG = re.compile(r"<\s*/?\s*(script|img|iframe|object|embed|a)\b[^>]*>",
                       re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_DATA_URI = re.compile(r"data:[^;\s]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)

REDACTION = "[link removed]"


def sanitise_text(text: str) -> tuple[str, int]:
    """Strip anything that could exfiltrate on render. Returns (text, n_removed)."""
    if not text:
        return text, 0
    removed = 0

    def _sub(pattern: re.Pattern[str], replacement: str, s: str) -> str:
        nonlocal removed
        s, n = pattern.subn(replacement, s)
        removed += n
        return s

    text = _sub(_DATA_URI, "[embedded data removed]", text)
    text = _sub(_MD_IMAGE, "[image removed]", text)
    text = _sub(_MD_LINK, r"\1", text)          # keep the label, drop the target
    text = _sub(_HTML_TAG, "", text)
    text = _sub(_URL, REDACTION, text)
    text = _sub(_EMAIL, "[address removed]", text)
    return text, removed


def _walk_strings(draft: ClaimDraft):
    """Yield (setter, value) for every free-text field we return to a client."""
    for li in draft.line_items:
        yield (lambda v, o=li: setattr(o, "label", v)), li.label, f"line_items.{li.item_id}.label"
        yield (lambda v, o=li: setattr(o, "rationale", v)), li.rationale, f"line_items.{li.item_id}.rationale"
    for h in draft.hazards:
        yield (lambda v, o=h: setattr(o, "action", v)), h.action, f"hazards.{h.item_id}.action"
    for n in draft.needs_human_review:
        yield (lambda v, o=n: setattr(o, "reason", v)), n.reason, f"needs_human.{n.item_id}.reason"
    for t in draft.model_trace:
        yield (lambda v, o=t: setattr(o, "note", v)), t.note, f"trace.{t.agent}.note"


def scrub(draft: ClaimDraft, *, canary: str | None = None) -> ClaimDraft:
    """Sanitise every outbound string and append any output-side findings."""
    findings: list[SecurityFinding] = []
    total_removed = 0

    for setter, value, path in list(_walk_strings(draft)):
        cleaned, removed = sanitise_text(value or "")
        if removed:
            total_removed += removed
            findings.append(SecurityFinding(
                source=path, channel=Channel.vlm_output,
                snippet=(value or "")[:200],
                rule="OUT_link_or_embed_redacted", layer="output",
                severity="medium", action_taken="stripped",
            ))
        if cleaned != value:
            setter(cleaned)

    # Finding snippets are rendered in the adjuster console, so they are an
    # outbound surface too. We keep the offending words visible — that is the
    # point of the highlight — but never the live link or address.
    for f in draft.security_findings:
        cleaned, removed = sanitise_text(f.snippet or "")
        if removed:
            total_removed += removed
            f.snippet = cleaned

    # Canary: if the system prompt leaked, it will show up here.
    if canary:
        blob = _render(draft)
        if canary in blob:
            findings.append(SecurityFinding(
                source="claim_draft", channel=Channel.vlm_output,
                snippet="[canary redacted]",
                rule="OUT_canary_leak", layer="canary",
                severity="critical", action_taken="blocked",
            ))
            for setter, value, _ in list(_walk_strings(draft)):
                if canary in (value or ""):
                    setter((value or "").replace(canary, "[redacted]"))

    # Second pass: run the rule layer over what we are about to return.
    for _, value, path in list(_walk_strings(draft)):
        if not value:
            continue
        hits = guard.run_rules(value, source=f"output:{path}", channel=Channel.vlm_output)
        for h in hits:
            h.layer = "output"
            h.action_taken = "flagged_only"
            findings.append(h)

    draft.security_findings.extend(findings)
    return draft


def _render(draft: ClaimDraft) -> str:
    return " ".join(
        v or "" for _, v, _ in _walk_strings(draft)
    )


def decision_blob(draft: ClaimDraft) -> dict[str, str]:
    """Decision-bearing text, for the flow-control substring check."""
    out: dict[str, str] = {}
    for li in draft.line_items:
        out[f"line_items.{li.item_id}.rationale"] = li.rationale
        out[f"line_items.{li.item_id}.peril"] = li.peril.value
        out[f"line_items.{li.item_id}.coverage"] = li.coverage.value
    for h in draft.hazards:
        out[f"hazards.{h.item_id}.action"] = h.action
    for n in draft.needs_human_review:
        out[f"needs_human.{n.item_id}.reason"] = n.reason
    return out
