"""Voice Notes agent (agent 7): a spoken sentence -> a guarded answer or a PROPOSED edit.

Pipeline for one transcript (from LiveKit STT or Safari speech recognition):
  1. guard.inspect(channel=voice_transcript). Anyone near the mic can speak, so a
     blocked transcript is refused outright: no LLM ever reads it.
  2. Nemotron (thinking off, quarantined: spotlit input, no tools, JSON only)
     classifies intent and extracts proposals. It returns ONLY
       {intent, topic, updates:[{item_id, field, value}]}
     with topic and field from closed enums and item_id from the manifest.
  3. The spoken reply is a TEMPLATE filled from the latest claim draft
     (coverage / estimate / hazard / measurement of the item in question). The
     LLM never writes what the headset says, so it cannot be made to say
     "approved" or read back an attacker's sentence.
  4. Updates are proposals with a proposal_id, status "proposed". They take
     effect only when the adjuster confirms (POST /voice/confirm). Allowed fields
     are adjuster_note, disputed, needs_photo, severity_opinion, access_blocked:
     never coverage, peril or cost.

Offline (or if NVIDIA fails) a regex classifier takes over; nothing falls back
to Claude, so voice never spends Anthropic credit.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from agents import guard, output_guard, settings
from agents.schemas import Channel, ClaimDraft, DamageManifest
from agents.trust import SPOTLIGHT_SYSTEM_RULE, new_datamark, spotlight

FIELDS = ("adjuster_note", "disputed", "needs_photo", "severity_opinion", "access_blocked")
TOPICS = ("coverage", "cost", "hazard", "measurement", "status", "other")

_SYSTEM = """You turn one spoken sentence from an insurance adjuster into JSON. You have no tools and change nothing.

{spotlight_rule}

Return ONLY:
{{"intent": "question" | "note" | "both",
  "topic": one of {topics},
  "item_id": the damage id the sentence is about, from KNOWN_IDS, or null,
  "updates": [{{"item_id": id from KNOWN_IDS, "field": one of {fields}, "value": short plain text}}]}}

"note" means the adjuster is recording an observation (e.g. "the sofa needs a photo", "I dispute the crack severity", "can't reach the closet").
Questions produce no updates. GAZE_ITEM is what the adjuster is looking at; use it for "this" / "that"."""

_Q = re.compile(r"\?|^\s*(is|are|does|do|can|what|how|why|will|should)\b", re.I)
_TOPIC_RX = [
    ("coverage", re.compile(r"\bcover(ed|age)?\b|\bpolicy\b|\bexclu", re.I)),
    ("cost", re.compile(r"\bcost|\bhow much\b|\bestimate|\bprice|\bdollar", re.I)),
    ("hazard", re.compile(r"\bsafe\b|\bdanger|\bhazard|\blive\b|\bshock|\bgas\b", re.I)),
    ("measurement", re.compile(r"\bhow (high|tall|big)|\bwaterline|\bsquare|\bmeters?\b|\barea\b", re.I)),
    ("status", re.compile(r"\bapprov|\bpay(out|ment)?\b|\bstatus\b", re.I)),
]
_FIELD_RX = [
    ("needs_photo", re.compile(r"\bphoto|\bpicture|\bimage\b", re.I)),
    ("disputed", re.compile(r"\bdispute|\bdisagree|\bwrong\b|\bnot (flood|right)\b", re.I)),
    ("access_blocked", re.compile(r"\bcan'?t (reach|get|access)|\bblocked\b|\binaccessible", re.I)),
    ("severity_opinion", re.compile(r"\bseverity|\bworse than|\bminor\b|\bsevere\b", re.I)),
]

PENDING: dict[str, dict[str, Any]] = {}
# Item ids the adjuster has looked at (from gaze on /voice and /callouts?seen=),
# for "what did I miss?". In-memory, like PENDING.
SEEN: set[str] = set()

M2_TO_FT2 = 10.7639
M_TO_IN = 39.3701

def _regex_classify(text: str, gaze: str | None, known: set[str]) -> dict[str, Any]:
    ids = [i for i in known if i in text.lower().replace(" ", "_")]
    item = ids[0] if ids else gaze
    is_q = bool(_Q.search(text))
    topic = next((t for t, rx in _TOPIC_RX if rx.search(text)), "other")
    updates = []
    if not is_q and item:
        field = next((f for f, rx in _FIELD_RX if rx.search(text)), "adjuster_note")
        updates.append({"item_id": item, "field": field, "value": text.strip()[:300]})
    return {"intent": "question" if is_q else "note", "topic": topic, "item_id": item,
            "updates": updates, "classifier": "regex"}


def _llm_classify(text: str, gaze: str | None, known: set[str]) -> dict[str, Any] | None:
    from agents.llm import nvidia_chat
    mark = new_datamark()
    system = _SYSTEM.format(spotlight_rule=SPOTLIGHT_SYSTEM_RULE.format(mark=mark),
                            topics=list(TOPICS), fields=list(FIELDS))
    user = (f"KNOWN_IDS: {sorted(known)}\nGAZE_ITEM: {gaze or 'none'}\n"
            + spotlight(text, mark, "voice"))
    try:
        comp = nvidia_chat("intake", [{"role": "system", "content": system},
                                      {"role": "user", "content": user}],
                           max_tokens=600, temperature=0.0,
                           extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        raw = comp.text
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:  # noqa: BLE001 - regex fallback
        return None
    intent = data.get("intent") if data.get("intent") in ("question", "note", "both") else "note"
    topic = data.get("topic") if data.get("topic") in TOPICS else "other"
    item = data.get("item_id") if data.get("item_id") in known else gaze
    updates = []
    for u in data.get("updates") or []:
        if (isinstance(u, dict) and u.get("item_id") in known and u.get("field") in FIELDS
                and isinstance(u.get("value"), str)):
            updates.append({"item_id": u["item_id"], "field": u["field"],
                            "value": u["value"].strip()[:300]})
    return {"intent": intent, "topic": topic, "item_id": item, "updates": updates[:5],
            "classifier": comp.model}


# ---------------------------------------------------------------------------
# Routing. One question -> one template answer from the claim draft and
# house_geometry.json (never LLM text). Order matters:
#   1. explicit intents that name no item: approval/payment, injection, help,
#      summary, room ranking, power safety, missed items
#   2. an ITEM: named out loud > "this/that/it" + gaze > gaze when the question
#      has no other subject. A named or gazed item beats a room word.
#   3. a ROOM summary/size (only when no item is meant)
#   4. house-wide topics: water height, flood cut/drywall, mold, hazards,
#      coverage, cost
#   5. otherwise the help line (never the claim total)
# ---------------------------------------------------------------------------

_RX = {
    "approval": re.compile(r"\bapprov\w*|\bauthori[sz]\w*|\bpay(out|ment|ing)?\b|\bpaid\b|\bsign(ed)? off\b"
                           r"|\bstatus\b|\bfinali[sz]ed?\b", re.I),
    "injection": re.compile(r"\btrick\w*|\binject\w*|\bmanipulat\w*|\bhack\w*|\bfool\w*|\btamper\w*"
                            r"|\bgam(e|ing) the (system|ai|claim)|\bcheat\w*|\bscam\w*|\bsabotag\w*|\bsocial engineer\w*"
                            r"|\bprompt injection|\bjailbreak\w*|\bmislead\w*|\bdeceiv\w*"
                            r"|\bprompt attack|\bsticky\b|\b(the|that|this) note\b|\bnote (on|left)\b|\bwritten on\b|\bmessage (on|left)\b", re.I),
    "help": re.compile(r"^\s*(hi|hello|hey|yo|good (morning|afternoon|evening)|test(ing)?|can you hear me)\b[\s.!?]*$"
                       r"|\bwhat can (you|i) (do|ask)\b|\bhelp\b|\bhow does this work\b|\bwho are you\b", re.I),
    "summary": re.compile(r"\bsummar\w*|\boverview\b|\bsum (it )?up\b|\brecap\b|\bbig picture\b|\bbottom line\b"
                          r"|\bwhole (claim|situation)\b.*\b(look|stand)|\bwhere do we stand\b", re.I),
    "rank_rooms": re.compile(r"\b(which|what) room\b|\bworst room\b|\brooms?\b.*\b(most|worst|least|rank)\b"
                             r"|\b(most|worst)\b.*\broom\b|\b(where|which part)\b.*\b(worst|most|biggest|heaviest)\b.*\b(damage|loss|hit)\w*", re.I),
    "power": re.compile(r"\bpower\b|\belectric\w*|\bbreaker\w*|\benergi[sz]\w*|\bcircuit\w*|\bwiring\b|\blights? on\b"
                        r"|\bplug\w*\b|\bshock\w*", re.I),
    "missed": re.compile(r"\bmiss(ed|ing)?\b|\bhaven'?t (looked|seen|checked|inspected)|\bnot (yet )?(inspected|checked|seen|looked)"
                         r"|\bleft to (inspect|check|see|look)|\bwhat else\b|\bstill (need|to) (inspect|check|look)"
                         r"|\bdid i (skip|overlook|forget)|\bremaining\b", re.I),
    "mold": re.compile(r"\bmou?ld\w*|\bspores?\b|\bmildew\b", re.I),
    "drywall": re.compile(r"\bflood[- ]?cut\b|\bdry\s?wall\b|\bsheet\s?rock\b|\bgypsum\b|\bplaster\s?board\b|\bwallboard\b", re.I),
    "waterline": re.compile(r"\bwater\s?line\b|\bhigh[- ]water\b|\bflood (level|line|height)\b"
                            r"|\bhow (high|deep|tall)\b.*\b(water|flood\w*)\b|\b(water|flood\w*)\b.*\b(height|level|reach\w*|rise|rose|deep|depth|high|get|got|come up|came up)\b", re.I),
    "hazard": re.compile(r"\bsafe\w*\b|\bdanger\w*|\bhazard\w*|\brisk\w*|\bunsafe\b|\bharm\w*|\bhurt\b|\bstructural\b", re.I),
    "coverage": re.compile(r"\bcover\w*|\bpolic(y|ies)\b|\bexclu\w*|\binsur\w*|\bclaimable\b|\bpay for\b|\bpays for\b", re.I),
    "cost": re.compile(r"\bcost\w*|\bhow much\b|\bestimat\w*|\bpric\w*|\bdollars?\b|\bworth\b|\bexpens\w*|\bbudget\b|\btotal\b", re.I),
    "size": re.compile(r"\bhow (big|large)\b|\barea\b|\bsquare (feet|foot|meters?|metres?)\b|\bsize\b|\bfloor space\b|\bdimensions?\b", re.I),
    "action": re.compile(r"\bwhat (should|do|can|must) (i|we)\b|\bwhat to do\b|\bdo about\b|\bnext steps?\b|\bhow (do|should) (i|we) (handle|deal|fix)\b"
                         r"|\bwho (do|should) (i|we) call\b|\brecommend\w*\b", re.I),
    "deixis": re.compile(r"\b(this|that|it|these|those|here)\b", re.I),
    "house": re.compile(r"\b(house|home|property|building|everything|overall|whole|all|every)\b", re.I),
}
# Words that name a TOPIC, not one item ("is there mold?", "where's the waterline?").
_TOPIC_WORDS = {"mold", "mould", "waterline", "line", "band", "mud", "silt", "stain", "growth"}
# Requests to change money or coverage by voice: always a fixed refusal.
_CHANGE_RX = re.compile(r"\b(set|change|raise|increase|bump|lower|reduce|make|put|mark|update|adjust|double)\b"
                        r".{0,60}\b(estimate|cost|price|payout|amount|total|coverage|covered|peril|value|dollars?)\b",
                        re.I)
# Everyday words mapped onto the words items are labelled with.
_SYNONYMS = {"computer": "laptop", "notebook": "laptop", "pc": "laptop", "macbook": "laptop",
             "wifi": "router", "wi-fi": "router", "modem": "router", "internet": "router",
             "television": "tv", "telly": "tv", "couch": "sofa", "settee": "sofa", "carpet": "rug",
             "fridge": "refrigerator", "floorboards": "planks", "flooring": "planks",
             "boiler": "furnace", "hvac": "furnace", "heating": "furnace", "socket": "outlet",
             "sockets": "outlets", "cupboards": "cabinets", "cupboard": "cabinet", "skirting": "baseboard"}
_SEV_WORD = {0: "undamaged", 1: "minor", 2: "moderate", 3: "significant", 4: "severe", 5: "critical"}
_CLAUSE = re.compile(r"\b(?:[A-Z]{2}-[A-Z]{2,5}-\d+|ADJ-\d+)\b")
HELP_LINE = ("Ask about the item you're looking at, a room, how high the water got, drywall, mold, "
             "hazards, coverage, costs, a claim summary, or what you haven't inspected yet.")

_ROOM_WORDS = [("hallway_closet", re.compile(r"\bcloset\b|\butility\b", re.I)),
               ("living_room", re.compile(r"\bliving\s*room\b|\blounge\b|\bfamily room\b", re.I)),
               ("kitchen", re.compile(r"\bkitchen\b", re.I)),
               ("hallway", re.compile(r"\bhall(way)?\b|\bcorridor\b|\bentry\w*\b", re.I))]
_STOP = {"the", "and", "with", "near", "run", "lower", "east", "north", "on", "of", "top", "in", "is",
         "high", "water", "wall", "floor", "damaged", "damage", "flooded", "submerged", "hazard",
         "house", "all", "living", "room", "kitchen", "hallway", "closet", "growth", "residual",
         "shelf", "bookshelf", "partition", "dislodged", "waterlogged", "soaked", "swollen", "flood",
         "electrical", "lower", "over", "tipped", "warped"}


def _usd(x: float) -> str:
    """Whole dollars, half rounded up (matches the console and the report)."""
    from decimal import ROUND_HALF_UP, Decimal
    return f"{int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}"


def _safe(text: str, n: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9 ,.'/()-]", "", str(text).replace("_", " "))[:n].strip() or "an item"


def _geometry() -> dict[str, Any]:
    p = settings.CONTRACTS_DIR / "samples" / "house_geometry.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _room_in(text: str) -> str | None:
    return next((rid for rid, rx in _ROOM_WORDS if rx.search(text)), None)


def _room_of(item) -> str | None:
    """A room named in the item's id/label wins (the hallway crack sits on the
    living-room boundary), else its position inside a room's floor polygon."""
    named = _room_in(item.id.replace("_", " ") + " " + item.label)
    if named:
        return named
    pos = getattr(item, "position", None)
    if pos is None:
        return None
    for r in _geometry().get("rooms", []):
        poly = [(p["x"], p["z"]) for p in r.get("floorPolygon", [])]
        inside = False
        for i in range(len(poly)):
            (x1, z1), (x2, z2) = poly[i], poly[i - 1]
            if (z1 > pos.z) != (z2 > pos.z) and pos.x < (x2 - x1) * (pos.z - z1) / (z2 - z1 + 1e-12) + x1:
                inside = not inside
        if inside:
            return r["id"]
    return None


def _name(item) -> str:
    """Spoken label; adds the room when the label alone is ambiguous."""
    label = _safe(item.label, 60)
    if re.search(r"outlet|debris|baseboard|mold|cabinet", item.label, re.I):
        rid = _room_of(item)
        if rid and rid.replace("_", " ") not in label.lower():
            label += f" ({rid.replace('_', ' ')})"
    return label


def _find_item(text: str, manifest: DamageManifest | None, gaze: str | None) -> str | None:
    """An item the adjuster NAMES out loud ("the laptop", "the TV", "the crack in
    the hallway"), or None. Ties: the gazed item, then the item in the named room."""
    if not manifest:
        return None
    low = text.lower()
    flat = low.replace(" ", "_")
    for it in manifest.items:
        if it.id in flat:
            return it.id
    # Everyday words for the same thing ("computer" = laptop, "couch" = sofa).
    for word, canon in _SYNONYMS.items():
        low = re.sub(rf"\b{word}\b", canon, low)
    room = _room_in(text)
    scored = []
    for it in manifest.items:
        ok = lambda w: w not in _STOP and w not in _TOPIC_WORDS and len(w) >= (2 if w == "tv" else 3)  # noqa: E731
        id_words = {w for w in it.id.split("_") if ok(w)}
        label_words = {w for w in re.findall(r"[a-z]{2,}", it.label.lower()) if ok(w)} - id_words
        hit = lambda w: re.search(rf"\b{w}(s|es)?\b", low) is not None  # noqa: E731
        # A word in the item's own id ("water_heater_flooded") counts double: it
        # is what the item IS; label-only words ("outlet near water heater") are context.
        score = 2 * sum(hit(w) for w in id_words) + sum(hit(w) for w in label_words)
        if score:
            scored.append(((score, int(it.id == gaze), int(room is not None and _room_of(it) == room)), it.id))
    if not scored:
        return None
    scored.sort(reverse=True)
    # Several items match equally (e.g. four outlets) and nothing breaks the tie:
    # nothing specific was named.
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _clauses(li) -> list[str]:
    found = ([li.exclusion_ref] if li.exclusion_ref else []) + _CLAUSE.findall(li.rationale or "")
    return list(dict.fromkeys(found))[:2]


def _item_answer(item_id: str, focus: str, draft: ClaimDraft, manifest: DamageManifest | None) -> tuple[str, list[str]]:
    """One rich answer about one item. The part the question asked about goes first."""
    items = {i.id: i for i in (manifest.items if manifest else [])}
    it = items.get(item_id)
    li = next((x for x in draft.line_items if x.item_id == item_id), None)
    hz = next((h for h in draft.hazards if h.item_id == item_id), None)
    label = _name(it) if it else _safe(item_id)
    cites = [f"manifest:{item_id}"]
    if it is not None and it.is_undamaged:
        wl = _geometry().get("waterlineHeight", {}).get("m", 0.9)
        return (f"{label}: undamaged, above the {wl:.1f} meter waterline, so there is nothing to cover. "
                f"A claim for it gets flagged.", cites)
    if li is None and hz is None:
        return (f"There is no claim line for {label}.", cites)

    parts: dict[str, str] = {}
    sev = it.severity if it else None
    parts["what"] = f"{_SEV_WORD.get(sev, 'recorded').capitalize()} damage" + (f" (severity {sev} of 5)." if sev else ".")
    if li is not None:
        q = li.quantity or {}
        if q.get("value"):
            unit = {"m2": "square meters", "m": "meters"}.get(q.get("unit"), q.get("unit", ""))
            parts["measure"] = f"Measured {q['value']:g} {unit} of {q.get('kind', '').replace('_m2', '').replace('_m', '').replace('_', ' ')}."
        parts["cost"] = f"Estimate {_usd(li.estimate.low_usd)} to {_usd(li.estimate.high_usd)} dollars."
        cl = _clauses(li)
        parts["coverage"] = (f"{li.peril.value.replace('_', ' ').capitalize()}, {li.coverage.value.replace('_', ' ')}"
                             + (f", {', '.join(cl)}" if cl else "") + ".")
        cites += [f"costs:{item_id}"] + [f"policy:{c}" for c in cl]
    if hz is not None:
        act = hz.action.split(". ")
        act_txt = ". ".join(act[:2]).rstrip(".") + "."
        parts["hazard"] = (f"Priority {hz.priority} {hz.hazard_type.replace('gas_co', 'gas and carbon monoxide').replace('_', ' ')} "
                           f"hazard: {act_txt}")
        cites.append(f"hazard:{item_id}")
    elif focus in ("hazard", "action"):
        parts["hazard"] = "No safety hazard is recorded for it."

    order = {"coverage": ["coverage", "what", "cost", "hazard", "measure"],
             "cost": ["cost", "what", "measure", "coverage", "hazard"],
             "hazard": ["hazard", "what", "coverage", "cost", "measure"],
             "action": ["hazard", "what", "coverage", "cost", "measure"],
             "size": ["measure", "what", "cost", "coverage", "hazard"]}.get(
                 focus, ["what", "measure", "cost", "coverage", "hazard"])
    text = f"{label}:"
    for k in order:
        if k in parts and len(text) + len(parts[k]) + 1 <= 300:
            text = (text + " " + parts[k]).strip()
    return text[:300], cites


def _focus(text: str) -> str:
    for k in ("action", "hazard", "coverage", "cost", "size"):
        if _RX[k].search(text):
            return k
    return "general"


def _summary(draft: ClaimDraft) -> tuple[str, list[str]]:
    t = draft.totals
    top = sorted(draft.hazards, key=lambda h: h.priority)[:2]
    wdr = sum(1 for li in draft.line_items if li.peril.value == "wind_driven_rain")
    flags = len(draft.needs_human_review)
    blocked = sum(1 for f in draft.security_findings if f.action_taken == "blocked")
    hz = ", ".join(h.hazard_type.replace("gas_co", "gas").replace("_", " ") for h in top)
    return (f"Draft claim: {t.item_count} items, {_usd(t.low_usd)} to {_usd(t.high_usd)} dollars. "
            f"{len(draft.hazards)} hazards, most urgent {hz}. {t.item_count - wdr} flood, {wdr} wind-driven rain "
            f"on homeowners. {flags} need your review"
            + (f", {blocked} injection attempts blocked." if blocked else "."), ["claim:totals"])


def _room_totals(draft: ClaimDraft, manifest: DamageManifest | None) -> dict[str, list]:
    from agents.pipeline import measure
    items = {i.id: i for i in (manifest.items if manifest else [])}
    out: dict[str, list] = {}
    for li in draft.line_items:
        it = items.get(li.item_id)
        rooms = measure.rooms_for(li.item_id)
        if len(rooms) > 1:
            continue  # house-wide lines (mud, waterline) belong to no single room
        rid = _room_of(it) if it else (rooms[0] if rooms else None)
        if rid:
            out.setdefault(rid, []).append(li)
    return out


def route(text: str, gaze: str | None, draft: ClaimDraft | None,
          manifest: DamageManifest | None) -> tuple[str, list[str]]:
    if _CHANGE_RX.search(text):
        return ("Voice can't change cost, coverage or peril. Those come from the policy and the rate table; "
                "record a note or dispute and decide it in the console.", ["claim:status"])
    if _RX["approval"].search(text) and not _RX["coverage"].search(text):
        return ("This claim is a draft. Only the adjuster can approve it or release payment; no agent can.",
                ["claim:status"])
    if draft is None:
        return ("No assessment has run yet. Run the claim first.", [])
    if _RX["help"].search(text):
        return (HELP_LINE, [])
    if _RX["injection"].search(text):
        notes_ = manifest.scene_text if manifest else []
        blocked = sum(1 for f in draft.security_findings if f.action_taken == "blocked")
        return ("Yes. A note in the scene is written to the AI, not to you: it tries to change the claim. "
                f"The guard blocked it, it changed nothing, and it is logged"
                + (f" ({blocked} blocked findings)." if blocked else "."),
                [f"scene_text:{n.id}" for n in notes_] or ["claim:security_findings"])
    if _RX["summary"].search(text):
        return _summary(draft)

    items = {i.id: i for i in (manifest.items if manifest else [])}
    lines = {li.item_id: li for li in draft.line_items}
    hazards = {h.item_id: h for h in draft.hazards}

    if _RX["rank_rooms"].search(text) and not _find_item(text, manifest, None):
        rt = _room_totals(draft, manifest)
        if rt:
            from agents.pipeline import measure
            rs = measure.rooms()
            ranked = sorted(rt.items(), key=lambda kv: -sum(li.estimate.high_usd for li in kv[1]))
            parts = [f"{rs.get(r, {}).get('label', r)} {_usd(sum(li.estimate.low_usd for li in ls))} to "
                     f"{_usd(sum(li.estimate.high_usd for li in ls))} dollars" for r, ls in ranked[:3]]
            return ("Most damage: " + "; then ".join(parts) + ".", [f"geometry:{r}" for r, _ in ranked[:3]])

    if _RX["missed"].search(text):
        damaged = [i for i in items.values() if not i.is_undamaged and i.id in lines]
        todo = sorted((i for i in damaged if i.id not in SEEN),
                      key=lambda i: (hazards[i.id].priority if i.id in hazards else 9, -i.severity))
        if not todo:
            return ("You have looked at every damaged item.", ["claim:line_items"])
        names = "; ".join(_name(i) for i in todo[:3])
        lead = (f"You haven't looked at {len(todo)} of {len(damaged)} damaged items." if SEEN
                else f"I have no gaze history yet, so all {len(damaged)} damaged items are not inspected.")
        return (f"{lead} Most urgent: {names}.", [f"manifest:{i.id}" for i in todo[:3]])

    named = _find_item(text, manifest, gaze)
    room = _room_in(text)
    house_wide = bool(_RX["house"].search(text))
    # The item meant: named > "this/that" + gaze > gaze when nothing else is the subject.
    item_id = named
    if item_id is None and gaze in items:
        topical = any(_RX[k].search(text) for k in ("mold", "drywall", "waterline", "power"))
        if _RX["deixis"].search(text) and not house_wide:
            item_id = gaze
        elif not room and not house_wide and not topical:
            item_id = gaze

    if _RX["power"].search(text) and not named:
        elec = [h for h in draft.hazards if h.hazard_type == "electrical"]
        if elec:
            rooms_ = list(dict.fromkeys((_room_of(items[h.item_id]) or "house").replace("_", " ")
                                        for h in elec if h.item_id in items))
            return (f"No. Do not energize: {len(elec)} submerged outlets or electrical hazards "
                    f"({', '.join(rooms_)}). A licensed electrician must inspect and replace submerged "
                    f"components before power is restored.", [f"hazard:{h.item_id}" for h in elec])

    if item_id is not None:
        return _item_answer(item_id, _focus(text), draft, manifest)

    g = _geometry()
    wl = g.get("waterlineHeight", {}).get("m")
    fc = g.get("floodCutHeight", {}).get("m")

    if _RX["mold"].search(text):
        molds = [i for i in items.values() if re.search(r"mou?ld", i.id + " " + i.label, re.I)]
        if room:
            molds = [i for i in molds if _room_of(i) == room] or molds
        if not molds:
            return ("No mold is recorded in this house.", ["manifest"])
        where = "; ".join(_name(i) for i in molds)
        cov = {lines[i.id].coverage.value.replace("_", " ") for i in molds if i.id in lines}
        act = next((hazards[i.id].action for i in molds if i.id in hazards), "")
        act = act.split(".")[0] + "." if act else ""
        return (f"{len(molds)} mold area{'s' if len(molds) != 1 else ''}: {where}. {act} "
                f"Coverage: {', '.join(sorted(cov)) or 'not set'}.", [f"manifest:{i.id}" for i in molds])

    if _RX["drywall"].search(text) and fc is not None:
        from agents.pipeline import measure
        rs = measure.rooms()
        if room and room in rs:
            a = rs[room]["flood_cut_m2"]
            return (f"{rs[room]['label']}: {a:.2f} square meters of drywall ({a * M2_TO_FT2:,.0f} square "
                    f"feet), flood cut to {fc:.1f} meters.", [f"geometry:{room}"])
        total = sum(r["flood_cut_m2"] for r in rs.values())
        li = next((x for x in lines.values() if (x.quantity or {}).get("kind") == "flood_cut_m2"), None)
        msg = (f"Flood cut to {fc:.1f} meters: {total:.1f} square meters of drywall "
               f"({total * M2_TO_FT2:,.0f} square feet) across {len(rs)} rooms.")
        if li:
            msg += f" Estimated {_usd(li.estimate.low_usd)} to {_usd(li.estimate.high_usd)} dollars."
        return (msg, ["geometry:floodCutHeight"] + ([f"costs:{li.item_id}"] if li else []))

    if _RX["waterline"].search(text) and wl is not None:
        msg = f"Water reached {wl:.2f} meters, about {wl * M_TO_IN:.0f} inches, on every wall."
        if fc is not None:
            msg += f" Drywall comes out to {fc:.1f} meters."
        return (msg, ["geometry:waterlineHeight"])

    if room:
        from agents.pipeline import measure
        rs = measure.rooms()
        label = rs.get(room, {}).get("label", room.replace("_", " ").title())
        if _RX["size"].search(text) and room in rs:
            r = rs[room]
            return (f"{label}: {r['floor_m2']:.1f} square meters of floor ({r['floor_m2'] * M2_TO_FT2:,.0f} "
                    f"square feet), {r['flood_cut_m2']:.2f} square meters of flood cut.", [f"geometry:{room}"])
        in_room = _room_totals(draft, manifest).get(room, [])
        if _RX["hazard"].search(text):
            hz_room = [hazards[li.item_id] for li in in_room if li.item_id in hazards]
            if not hz_room:
                return (f"No safety hazard is recorded in the {label.lower()}.", [f"geometry:{room}"])
            hz_room.sort(key=lambda h: h.priority)
            names = "; ".join(f"{_name(items[h.item_id])}, priority {h.priority}" for h in hz_room[:3])
            return (f"{label}: {len(hz_room)} hazards. {names}.", [f"hazard:{h.item_id}" for h in hz_room[:3]])
        if not in_room:
            return (f"No damage is recorded in the {label.lower()}.", [f"geometry:{room}"])
        in_room.sort(key=lambda li: -items[li.item_id].severity)
        low = sum(li.estimate.low_usd for li in in_room)
        high = sum(li.estimate.high_usd for li in in_room)
        names = "; ".join(_name(items[li.item_id]) for li in in_room[:4])
        more = f" and {len(in_room) - 4} more" if len(in_room) > 4 else ""
        return (f"{label}: {len(in_room)} damaged items, {_usd(low)} to {_usd(high)} dollars. "
                f"Worst: {names}{more}.", [f"manifest:{li.item_id}" for li in in_room[:4]])

    if _RX["hazard"].search(text):
        top = sorted(draft.hazards, key=lambda h: h.priority)[:3]
        if not top:
            return ("No safety hazards are recorded in this house.", ["claim:hazards"])
        kinds = {"gas_co": "gas and carbon monoxide"}
        parts = [f"{_name(items[h.item_id]) if h.item_id in items else h.item_id}, "
                 f"{kinds.get(h.hazard_type, h.hazard_type.replace('_', ' '))}" for h in top]
        more = len(draft.hazards) - len(top)
        return (f"{len(draft.hazards)} hazards. Most urgent: {'; '.join(parts)}."
                + (f" Plus {more} more." if more > 0 else ""), [f"hazard:{h.item_id}" for h in top])

    if _RX["coverage"].search(text):
        c = {k: sum(1 for x in draft.line_items if x.coverage.value == k)
             for k in ("flood_policy", "homeowners_policy", "excluded", "needs_human")}
        return (f"{c['flood_policy']} items under the flood policy, {c['homeowners_policy']} under homeowners, "
                f"{c['excluded']} excluded, {c['needs_human']} need your review. Look at an item for its reason.",
                ["claim:line_items"])

    if _RX["cost"].search(text):
        t = draft.totals
        return (f"The whole claim is estimated at {_usd(t.low_usd)} to {_usd(t.high_usd)} dollars.", ["claim:totals"])

    return (HELP_LINE, [])


def handle(transcript: str, *, gaze_item_id: str | None = None, standpoint: str | None = None,
           audit_trail_id: str | None = None, draft: ClaimDraft | None = None,
           manifest: DamageManifest | None = None) -> dict[str, Any]:
    blocked, findings = guard.inspect(transcript, source="voice", channel=Channel.voice_transcript)
    gfind = [{"rule": f.rule, "snippet": output_guard.sanitise_text(f.snippet)[0][:400],
              "layer": f.layer} for f in findings]
    if blocked:
        return {"kind": "refused",
                "spoken_reply": "I can't act on that. It sounded like an instruction to the system, "
                                "so it was blocked and logged.",
                "updates": [], "citations": [], "guard": {"blocked": True, "findings": gfind}}

    known = {i.id for i in manifest.items} if manifest else set()
    gaze = gaze_item_id if gaze_item_id in known else None
    cls = None
    if not settings.is_offline() and settings.has_key("nvidia"):
        cls = _llm_classify(transcript, gaze, known)
    cls = cls or _regex_classify(transcript, gaze, known)

    if gaze:
        SEEN.add(gaze)
    # Questions, plus anything that isn't a usable note ("hello", "summarize the claim").
    is_question = (cls["intent"] in ("question", "both") or bool(_Q.search(transcript))
                   or not cls["updates"])
    reply, cites = "", []
    if is_question:
        reply, cites = route(transcript, gaze, draft, manifest)
        if cls["intent"] == "note":  # a question was mis-read as a note: answer only
            cls = {**cls, "intent": "question"}

    updates = []
    if cls["intent"] in ("note", "both"):
        for u in cls["updates"]:
            pid = "vp_" + secrets.token_hex(4)
            value = output_guard.sanitise_text(u["value"])[0]
            rec = {"proposal_id": pid, "item_id": u["item_id"], "field": u["field"],
                   "value": value, "status": "proposed"}
            PENDING[pid] = {**rec, "audit_trail_id": audit_trail_id,
                            "created_at": datetime.now(timezone.utc).isoformat()}
            updates.append(rec)
        if updates:
            u0 = updates[0]
            note = (f"Proposed {u0['field'].replace('_', ' ')} on {u0['item_id'].replace('_', ' ')}"
                    + (f" and {len(updates) - 1} more" if len(updates) > 1 else "")
                    + ". Confirm to save.")
            reply = (reply + " " + note).strip() if reply else note
    if not reply:
        reply = "Noted, but I didn't catch an item or a question. Look at the item and try again."

    kind = ("both" if reply and updates and cls["intent"] == "both"
            else "update" if updates else "answer")
    return {"kind": kind, "spoken_reply": reply[:300], "updates": updates,
            "citations": cites, "guard": {"blocked": False, "findings": gfind},
            "classifier": cls["classifier"], "standpoint": standpoint}


def confirm(proposal_id: str, accept: bool) -> dict[str, Any]:
    rec = PENDING.get(proposal_id)
    if rec is None:
        return {"ok": False, "error": "unknown proposal_id"}
    if rec["status"] != "proposed":
        return {"ok": False, "error": f"already {rec['status']}"}
    rec["status"] = "confirmed" if accept else "rejected"
    rec["decided_at"] = datetime.now(timezone.utc).isoformat()
    return {"ok": True, "proposal": rec}
