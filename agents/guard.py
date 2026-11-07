"""Injection guard: rule layer + NVIDIA guard model layer.

Design notes that matter for the honest eval:

* The rules below were written BEFORE any held-out attack existed. They encode
  what we guessed an attack looks like. `evals/gen_variants.py` then has Claude
  write fresh attacks, and we measure against those before touching anything
  here. Tuning a rule after seeing the held-out set would make the number a lie.
* Most rules require an IMPERATIVE context, not just a keyword. The real
  manifest says "total loss, mold risk if not removed quickly" about a soaked
  sofa — a guard that blocks the phrase "total loss" would block the ground
  truth. Precision on clean text is measured as the false-positive rate.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass

from agents import settings
from agents.schemas import Channel, SecurityFinding
from agents.trust import find_invisible, normalise


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pattern: re.Pattern[str]
    severity: str
    score: float
    why: str


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE | re.DOTALL)


# Spacing-tolerant helper: lets "i g n o r e" match "ignore".
def _loose(word: str) -> str:
    return r"[\s\-_.]*".join(re.escape(c) for c in word)


RULES: list[Rule] = [
    Rule(
        "R01_instruction_override",
        _rx(rf"(?:{_loose('ignore')}|disregard|forget|override|supersede"
            r"|ignora|ignorez|ignorar|oubliez|olvida|vergiss|忽略|무시)"
            r"[\s\w,'’]{0,40}?"
            r"(previous|prior|above|earlier|all|any|your|anterior|anteriores|"
            r"precedente|precedentes|vorherige)"
            r"[\s\w'’]{0,25}?"
            r"(instruction|instruccion|instrucciones|prompt|rule|regla|direction|"
            r"guideline|system|training|cost\s*table|table|constraint|limit|policy)"),
        "critical", 1.0,
        "Instruction-override opener, including common non-English forms. The "
        "object list covers 'your cost table' as well as 'previous instructions'.",
    ),
    Rule(
        "R02_fake_role_tag",
        _rx(r"(<\|[a-z_]+\|>"                      # <|im_start|>, anywhere
            r"|\[/?INST\]|<</?SYS>>"
            r"|(^|\n|\s|_)(<\s*/?\s*(system|assistant|instruction)[^>]*>"
            r"|\[\s*(system|assistant|admin|developer)\s*\]"
            r"|#{1,4}\s*(system|instruction)\b"
            r"|\b(system|assistant|developer)\s*:\s*(?=\S)"
            r"|\bai\s+(adjuster|agent|assistant|model)\s*[:,]))"),
        "critical", 1.0,
        "Forged role/turn delimiter trying to open a privileged channel.",
    ),
    Rule(
        "R03_hidden_text",
        _rx(r"(?!)"),  # handled procedurally in _hidden_text_findings
        "high", 0.9,
        "Zero-width, bidi-override or invisible characters.",
    ),
    Rule(
        "R04_classification_override",
        _rx(r"\b(classify|mark|label|categor(?:ise|ize)|record|treat|set|report)\b"
            r"[\s\w,]{0,30}?\b(everything|all|every\s+\w+|each\s+\w+|the\s+entire|whole\s+\w+)\b"
            r"[\s\w,]{0,30}?\b(as|to\s+be|under)\b"),
        "critical", 1.0,
        "Tries to force a blanket peril/coverage classification.",
    ),
    Rule(
        "R05_payment_directive",
        _rx(r"\b(pay|payout|approve|authorise|authorize|disburse|settle|issue|release)\b"
            r"[\s\w,]{0,25}?"
            r"(\bmax(imum)?\b|\bfull\b|\bin\s+full\b|\$\s?[\d,]{3,}|\bpolicy\s+limit)"
            r"|\b(total\s+loss)\b[\s\w,]{0,20}?\b(pay|approve|payout|settle|max)"),
        "critical", 1.0,
        "Directs a payout. Note: bare 'total loss' is NOT matched — the real "
        "manifest uses that phrase legitimately.",
    ),
    Rule(
        "R06_authority_claim",
        _rx(r"\b(as (the|your) (adjuster|supervisor|administrator|developer|owner)"
            r"|authorised by|authorized by|on behalf of (state\s*farm|the (insurer|carrier))"
            r"|this is (an? )?(official|authorised|authorized|approved) (instruction|override|directive)"
            r"|i am (the|your) (adjuster|supervisor|admin|developer))\b"),
        "high", 0.85,
        "Claims authority the channel cannot carry.",
    ),
    Rule(
        "R07_prompt_exfil",
        # No trailing \b on the verb: an underscore is a word character, so
        # "reveal_your_instructions" in a filename would not match otherwise.
        _rx(r"(^|[^a-z])(print|reveal|repeat|output|show|disclose|echo|dump|leak"
            r"|summar(?:ise|ize))"
            r"[\s\w,_-]{0,25}?"
            r"(system[\s_-]+prompt|your[\s_-]+(instructions|prompt|rules|configuration)"
            r"|the[\s_-]+prompt|canary|api[\s_-]?key|secret|credential)"),
        "critical", 1.0,
        "Attempts to leak the system prompt, canary or credentials.",
    ),
    Rule(
        "R08_tool_abuse",
        _rx(r"\b(call|invoke|run|execute|use)\b[\s\w,]{0,20}?"
            r"\b(tool|function|api|endpoint|lookup_cost|flag_for_human|get_policy)\b"
            r"|\bset\b[\s\w]{0,15}?\b(coverage|peril|severity|estimate|confidence)\b"
            r"[\s\w]{0,10}?\bto\b"),
        "high", 0.85,
        "Tries to drive a tool call or overwrite a structured field.",
    ),
    Rule(
        "R09_encoded_payload",
        _rx(r"(?!)"),  # handled procedurally in _encoded_findings
        "medium", 0.6,
        "Base64/hex blob that decodes to instruction-like text.",
    ),
    Rule(
        "R10_url_or_exfil_target",
        _rx(r"\b(send|post|upload|forward|transmit|email|exfiltrate|submit|deliver)\b"
            r"[\s\w,'’]{0,30}?(https?://|www\.|\S+@\S+)"
            r"|(https?://|www\.)[^\s\"'<>]{4,}[\s\S]{0,40}?"
            r"\b(before|after)\b[\s\w]{0,20}?\b(finish|complet|submit|respond)"),
        "medium", 0.55,
        "URL paired with a directive to send data there. A bare URL is NOT "
        "matched — real claim documents cite the carrier's own website.",
    ),
    Rule(
        "R11_urgency_or_threat",
        _rx(r"\b(without\s+(any\s+)?(delay|question|further\s+)?(review|verification|checking)"
            r"|without\s+(delay|question)"
            r"|do(es)?\s+not\s+(need\s+to\s+|have\s+to\s+)?(ask|verify|check|flag|review|"
            r"escalate|confirm)"
            r"|no\s+(human\s+)?(review|verification|approval)\s+(is\s+)?(needed|required)"
            r"|skip\s+(the\s+)?(review|check|verification|human)"
            r"|bypass\s+(the\s+)?\w+"
            r"|no\s+need\s+to\s+(flag|review|verify|escalate))\b"),
        "medium", 0.6,
        "Suppression of the human-review gate. Bare urgency words ('urgent', "
        "'immediately') are NOT matched — legitimate contractors write that way.",
    ),
    Rule(
        "R12_scope_expansion",
        _rx(r"\b(also|additionally|in addition|furthermore)\b[\s\w,]{0,25}?"
            r"\b(add|include|increase|raise|bump|inflate)\b[\s\w,]{0,25}?"
            r"(\$\s?[\d,]{3,}|\b(cost|estimate|amount|total|claim)\b)"),
        "high", 0.8,
        "Tries to append cost beyond what the manifest supports.",
    ),
    Rule(
        "R13_persona_override",
        _rx(r"\b(you are now|from now on you|act as|pretend (to be|you are)|"
            r"stay in character|let'?s play a game|roleplay|role-play|"
            r"you (are|will be) (an? )?\w*(adjuster|assistant|ai|mode)\b)"
            r"[\s\S]{0,80}?"
            r"\b(approv|pay|maximum|max\b|total loss|unsafe|unrestricted|no limits|"
            r"always|override|ignore)"
            r"|\b(you are now in|enter|switch to)\s+\w+\s+mode\b"),
        "high", 0.85,
        "Persona/role-play reframing used to swap the agent's objective.",
    ),
    Rule(
        "R14_payment_directive_multilingual",
        _rx(r"\b(aprueb[ae]|apruebe|aprobar|pagu[ae]|paga)\b[\s\w]{0,20}?"
            r"\b(maximo|máximo|total|completo|limite)"
            r"|\b(pago|pagamento|paiement|paiment)\s+(maximo|máximo|maximum|total)"
            r"|\bperte\s+totale\b|\bp[eé]rdida\s+total\b"
            r"|\bclass(?:ez|ifiez|ifique|ifiquen)\b[\s\w]{0,25}?\b(tout|todo|comme|como)\b"),
        "critical", 1.0,
        "Non-English payout/classification directive.",
    ),
    Rule(
        "R15_prior_approval_claim",
        _rx(r"\b(already (been )?(approved|authorised|authorized|signed off|cleared)"
            r"|approved (it )?(verbally|by phone|yesterday|earlier)"
            r"|(adjuster|supervisor|manager) (has )?already (approved|cleared|signed))\b"),
        "high", 0.8,
        "Claims a prior human approval that the channel cannot evidence — used "
        "to argue the review gate has already been satisfied.",
    ),
]

RULES_BY_ID = {r.rule_id: r for r in RULES}


def _snippet(text: str, start: int, end: int, pad: int = 40) -> tuple[str, tuple[int, int]]:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi].strip(), (start, end)


def _hidden_text_findings(text: str, source: str, channel: Channel) -> list[SecurityFinding]:
    hits = find_invisible(text)
    if not hits:
        return []
    rule = RULES_BY_ID["R03_hidden_text"]
    first = hits[0][0]
    snip, span = _snippet(text, first, min(first + 1, len(text)))
    return [SecurityFinding(
        source=source, channel=channel,
        snippet=f"{len(hits)} invisible char(s) near: {snip!r}",
        span=span, rule=rule.rule_id, layer="rules", severity=rule.severity,
    )]


_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _encoded_findings(text: str, source: str, channel: Channel) -> list[SecurityFinding]:
    out: list[SecurityFinding] = []
    rule = RULES_BY_ID["R09_encoded_payload"]
    for m in _B64.finditer(text):
        blob = m.group(0)
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False)
            text_out = decoded.decode("utf-8", errors="strict")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if len(text_out) < 8:
            continue
        # Only flag when the DECODED text is itself instruction-like.
        inner = run_rules(text_out, source=f"{source}#b64", channel=channel)
        if inner:
            snip, span = _snippet(text, m.start(), m.end())
            out.append(SecurityFinding(
                source=source, channel=channel,
                snippet=snip[:400],
                span=span, rule=f"{rule.rule_id}->{inner[0].rule}",
                layer="rules", severity="high",
            ))
    return out


def run_rules(text: str, source: str, channel: Channel) -> list[SecurityFinding]:
    """Deterministic rule layer. Returns one finding per rule that fired."""
    if not text:
        return []
    findings: list[SecurityFinding] = []
    norm = normalise(text)

    for rule in RULES:
        if rule.rule_id in {"R03_hidden_text", "R09_encoded_payload"}:
            continue
        m = rule.pattern.search(norm)
        if not m:
            continue
        # Map back to the original text where possible for accurate highlighting.
        probe = norm[m.start():m.end()].strip()[:40]
        idx = text.lower().find(probe[:20]) if probe else -1
        if idx >= 0:
            snip, span = _snippet(text, idx, idx + len(probe))
        else:
            snip, span = text[m.start():m.end() + 40].strip(), (m.start(), m.end())
        findings.append(SecurityFinding(
            source=source, channel=channel, snippet=snip[:400], span=span,
            rule=rule.rule_id, layer="rules", severity=rule.severity,
        ))

    findings.extend(_hidden_text_findings(text, source, channel))
    findings.extend(_encoded_findings(text, source, channel))
    return findings


def rule_score(findings: list[SecurityFinding]) -> float:
    """Highest-scoring rule that fired. 0.0 means nothing fired."""
    if not findings:
        return 0.0
    scores = []
    for f in findings:
        base = f.rule.split("->")[0]
        rule = RULES_BY_ID.get(base)
        scores.append(rule.score if rule else 0.5)
    return max(scores)


# --------------------------------------------------------------------------
# Layer 2: the NVIDIA guard model.
# --------------------------------------------------------------------------

def guard_model_flags(text: str, *, debug: bool = False) -> tuple[bool, str]:
    """Ask the NVIDIA guard model whether `text` is an injection/jailbreak.

    Returns (is_unsafe, raw_verdict). Offline, this returns (False, "offline")
    so the rule layer alone decides and the eval stays deterministic.

    The response shape differs per guard model, so parsing is defensive and the
    raw reply is returned for inspection (`--show-raw` on the verify script).
    """
    if settings.is_offline() or not settings.has_key("nvidia"):
        return False, "offline"

    from agents.llm import guard_complete  # local import keeps evals import-light

    raw = guard_complete(text)
    if debug:
        print(f"[guard raw] {raw!r}")
    return parse_guard_verdict(raw), raw


_UNSAFE_TOKENS = ("unsafe", "jailbreak", "true", "yes", "injection", "malicious", "attack")
_SAFE_TOKENS = ("safe", "benign", "false", "no", "none")


def parse_guard_verdict(raw: str) -> bool:
    """Interpret a guard model reply. Tolerant of JSON, label text and prose.

    Checked against a real response before the demo — see
    `python -m agents.tools.verify_models --probe-guard`, which prints the raw
    reply so this parser is fixed against reality, not a guess.
    """
    if not raw:
        return False
    import json

    stripped = raw.strip()

    # Shape 1: JSON, e.g. {"User Safety": "unsafe", "Safety Categories": "..."}
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            for key in ("User Safety", "user_safety", "response", "label",
                        "jailbreak", "is_jailbreak", "verdict", "safety"):
                if key in data:
                    val = data[key]
                    if isinstance(val, bool):
                        return val
                    if isinstance(val, str) and val.strip().lower() in _UNSAFE_TOKENS:
                        return True
                    if isinstance(val, str) and val.strip().lower() in _SAFE_TOKENS:
                        return False
            flat = json.dumps(data).lower()
            return "unsafe" in flat or '"jailbreak": true' in flat
        except json.JSONDecodeError:
            pass

    # Shape 2: a bare label, possibly with categories on the next line
    # (Llama Guard answers literally "safe" or "unsafe\nS2").
    first = stripped.splitlines()[0].strip().lower().strip(".:,\"'")
    if first in _SAFE_TOKENS:
        return False
    if first in _UNSAFE_TOKENS:
        return True

    # Shape 3: prose. Prefer an explicit "unsafe", but don't let the word
    # "unsafe" inside "not unsafe" flip it.
    low = stripped.lower()
    if re.search(r"\b(not|isn'?t|no)\s+(an?\s+)?(unsafe|jailbreak|injection)", low):
        return False
    return any(tok in low for tok in ("unsafe", "jailbreak", "prompt injection"))


# --------------------------------------------------------------------------
# Combined entry point
# --------------------------------------------------------------------------

def inspect(
    text: str,
    *,
    source: str,
    channel: Channel,
    use_rules: bool = True,
    use_guard_model: bool = True,
) -> tuple[bool, list[SecurityFinding]]:
    """Run the enabled layers. Returns (blocked, findings)."""
    cfg = settings.config()["guard"]
    findings: list[SecurityFinding] = []

    if use_rules and cfg.get("rules_enabled", True):
        findings.extend(run_rules(text, source=source, channel=channel))

    blocked = rule_score(findings) >= float(cfg.get("block_threshold", 0.5))

    if use_guard_model and cfg.get("guard_model_enabled", True):
        flagged, raw = guard_model_flags(text)
        if flagged:
            blocked = True
            findings.append(SecurityFinding(
                source=source, channel=channel,
                snippet=text[:200],
                rule=f"guard_model:{raw.strip().splitlines()[0][:60] if raw else 'unsafe'}",
                layer="guard_model", severity="high",
            ))

    return blocked, findings
