"""Information-flow control, lightweight.

Microsoft's SFI guidance and the CaMeL paper both say the same thing: tracking
*provenance* and enforcing policy on it beats trying to detect bad text. We
cannot ship CaMeL's custom interpreter in a hackathon, so this is the honest
subset:

1.  Every decision-bearing field declares which sources produced it.
2.  A run fails its flow check if an UNTRUSTED source contributed to a peril,
    coverage or cost decision.
3.  Independently of (1) and (2), we verify empirically that no span of
    untrusted text appears in any decision-bearing field. Declarations can lie;
    a substring check cannot.

(3) is what makes this more than documentation. If an attacker's words ever
reach a coverage rationale, the run says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.schemas import TrustLabel

# Decision-bearing fields. If untrusted text reaches one of these, the claim has
# been influenced by the attacker, whatever the guard decided.
DECISION_FIELDS = ("peril", "coverage", "exclusion_ref", "estimate", "confidence",
                   "rationale", "priority", "action", "dispatch")

# Length of the word window used for the substring check. Six words is long
# enough that ordinary insurance vocabulary ("the living room floor is") does
# not collide by accident, short enough to catch a planted phrase.
SHINGLE_WORDS = 6

_WORD = re.compile(r"[a-z0-9$%.]+")


def _shingles(text: str, n: int = SHINGLE_WORDS) -> set[str]:
    words = _WORD.findall(text.lower())
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


@dataclass
class FlowViolation:
    field_path: str
    source: str
    trust: str
    detail: str


@dataclass
class Ledger:
    """Records which sources fed which decision, and checks the result."""

    entries: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    untrusted_texts: dict[str, str] = field(default_factory=dict)
    violations: list[FlowViolation] = field(default_factory=list)

    def record(self, field_path: str, source: str, trust: TrustLabel) -> None:
        self.entries.setdefault(field_path, set()).add((source, trust.value))

    def record_untrusted(self, source: str, text: str) -> None:
        """Remember an untrusted input so we can check the output against it."""
        if text and text.strip():
            self.untrusted_texts[source] = text

    def check_declarations(self) -> None:
        """Fail any decision field that declares an untrusted contributor."""
        for path, sources in self.entries.items():
            if not any(path.endswith(f) or f in path for f in DECISION_FIELDS):
                continue
            for source, trust in sources:
                if trust == TrustLabel.untrusted.value:
                    self.violations.append(FlowViolation(
                        field_path=path, source=source, trust=trust,
                        detail="an untrusted source contributed to a decision field",
                    ))

    def check_text_leakage(self, decision_blob: dict[str, str]) -> None:
        """Verify no span of untrusted text reached a decision field.

        `decision_blob` maps a field path to its rendered text.
        """
        if not self.untrusted_texts:
            return
        attacker: dict[str, set[str]] = {
            src: _shingles(text) for src, text in self.untrusted_texts.items()
        }
        for path, rendered in decision_blob.items():
            if not rendered:
                continue
            produced = _shingles(rendered)
            if not produced:
                continue
            for src, spans in attacker.items():
                overlap = produced & spans
                if overlap:
                    self.violations.append(FlowViolation(
                        field_path=path, source=src,
                        trust=TrustLabel.untrusted.value,
                        detail=f"untrusted text reached a decision field: "
                               f"{sorted(overlap)[0][:80]!r}",
                    ))

    @property
    def clean(self) -> bool:
        return not self.violations

    def summary(self) -> dict:
        return {
            "decision_fields_checked": len(self.entries),
            "untrusted_inputs_seen": len(self.untrusted_texts),
            "shingle_words": SHINGLE_WORDS,
            "clean": self.clean,
            "violations": [
                {
                    "field": v.field_path, "source": v.source,
                    "trust": v.trust, "detail": v.detail,
                }
                for v in self.violations
            ],
            "statement": (
                "No untrusted input contributed to any peril, coverage or cost "
                "decision in this run, verified by declaration and by substring "
                "check."
                if self.clean else
                f"{len(self.violations)} flow violation(s): untrusted input "
                f"reached a decision field."
            ),
        }
