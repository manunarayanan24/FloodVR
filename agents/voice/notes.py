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

_ROOM_WORDS = [("hallway_closet", re.compile(r"\bcloset\b", re.I)),
               ("living_room", re.compile(r"\bliving\s*room\b|\blounge\b", re.I)),
               ("kitchen", re.compile(r"\bkitchen\b", re.I)),
               ("hallway", re.compile(r"\bhall(way)?\b", re.I))]
_STOP = {"the", "and", "with", "near", "run", "lower", "east", "north", "on", "of", "top",
         "high", "water", "wall", "floor", "damaged", "damage", "flooded", "submerged",
         "hazard", "house", "all", "living", "room", "kitchen", "hallway", "closet"}


def _usd(x: float) -> str:
    """Whole dollars, half rounded up (matches the console and the report)."""
    from decimal import ROUND_HALF_UP, Decimal
    return f"{int(Decimal(str(x)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}"
_SPECIFIC = [
    ("scene_note", re.compile(r"\b(sticky|note|sign|written|writing)\b", re.I)),
    ("missed", re.compile(r"\bmiss(ed|ing)?\b|\bhaven'?t (looked|seen|checked)|\bnot (yet )?(inspected|checked|seen)"
                          r"|\bleft to (inspect|check|see|look)|\bwhat else\b|\bstill to (inspect|check)", re.I)),
    ("mold", re.compile(r"\bmou?ld\b|\bspores?\b|\bmildew\b", re.I)),
    ("contents", re.compile(r"\blaptop\b|\brouter\b|\belectronics?\b|\bundamaged\b|\bcomputer\b", re.I)),
    ("drywall", re.compile(r"\bflood[- ]?cut\b|\bdry\s?wall\b|\bsheetrock\b|\bgypsum\b|\bplaster\s?board\b", re.I)),
    ("waterline", re.compile(r"\bhow (high|deep)\b.*\bwater\b|\bwater\b.*\b(height|level|line|reach|rise|deep|high|get)\b"
                             r"|\bwaterline\b|\bhigh[- ]water\b", re.I)),
]
_COST_RX = re.compile(r"\bcost|\bhow much\b.*\b(cost|dollar|worth|price|is the)\b|\bprice|\bdollar|\bestimate", re.I)
_SIZE_RX = re.compile(r"\bhow (big|large)\b|\barea\b|\bsquare\b|\bsize\b|\bfloor space\b", re.I)


def _safe(text: str, n: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9 ,.'/()-]", "", str(text).replace("_", " "))[:n].strip() or "an item"


def _geometry() -> dict[str, Any]:
    p = settings.CONTRACTS_DIR / "samples" / "house_geometry.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _room_of(item) -> str | None:
    """Room id for a manifest item: a room named in its id/label wins (a crack in
    the hallway partition sits on the living-room boundary), else its position
    inside a room's floor polygon."""
    named = _room_in((item.id.replace("_", " ") + " " + item.label))
    if named:
        return named
    g = _geometry()
    pos = getattr(item, "position", None)
    if pos is None:
        return None
    x, z = pos.x, pos.z
    for r in g.get("rooms", []):
        poly = [(p["x"], p["z"]) for p in r.get("floorPolygon", [])]
        inside = False
        for i in range(len(poly)):
            (x1, z1), (x2, z2) = poly[i], poly[i - 1]
            if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1 + 1e-12) + x1:
                inside = not inside
        if inside:
            return r["id"]
    return None


def _find_item(text: str, manifest: DamageManifest | None, gaze: str | None) -> str | None:
    """Item id from an id spoken as words or distinctive label words ('the laptop')."""
    if not manifest:
        return gaze
    low = text.lower()
    flat = low.replace(" ", "_")
    for it in manifest.items:
        if it.id in flat:
            return it.id
    best, best_score = None, 0
    for it in manifest.items:
        words = {w for w in re.findall(r"[a-z]{3,}", (it.label + " " + it.id.replace("_", " ")).lower())
                 if w not in _STOP}
        score = sum(1 for w in words if re.search(rf"\b{w}s?\b", low))
        if score > best_score or (score == best_score and score and it.id == gaze):
            best, best_score = it.id, score
    return best if best_score else gaze


def _room_in(text: str) -> str | None:
    return next((rid for rid, rx in _ROOM_WORDS if rx.search(text)), None)


def _name(item) -> str:
    """Spoken label; adds the room when the label alone is ambiguous (outlets)."""
    label = _safe(item.label, 60)
    if re.search(r"outlet|debris|baseboard|mold|cabinet", item.label, re.I):
        rid = _room_of(item)
        if rid and rid.replace("_", " ") not in label.lower():
            label += f" ({rid.replace('_', ' ')})"
    return label


def _specific(text: str, item_id: str | None, draft: ClaimDraft | None,
              manifest: DamageManifest | None) -> tuple[str, list[str]] | None:
    """Template answers for the questions a generic topic can't handle.
    Every number comes from the claim draft or house_geometry.json."""
    kind = next((k for k, rx in _SPECIFIC if rx.search(text)), None)
    room = _room_in(text)
    g = _geometry()
    wl = g.get("waterlineHeight", {}).get("m")
    fc = g.get("floodCutHeight", {}).get("m")
    items = {i.id: i for i in (manifest.items if manifest else [])}
    lines = {li.item_id: li for li in (draft.line_items if draft else [])}
    hazards = {h.item_id: h for h in (draft.hazards if draft else [])}

    if kind == "scene_note":
        notes_ = manifest.scene_text if manifest else []
        if not notes_:
            return None
        return ("The note in the scene is written to the AI, not to you. It tells the system to "
                "change the claim. The guard blocked it and it changed nothing; it is logged as an "
                "injection attempt.", [f"scene_text:{n.id}" for n in notes_])

    if kind == "missed":
        damaged = [i for i in items.values() if not i.is_undamaged and i.id in lines]
        todo = sorted((i for i in damaged if i.id not in SEEN),
                      key=lambda i: (hazards[i.id].priority if i.id in hazards else 9, -i.severity))
        if not todo:
            return ("You have looked at every damaged item.", ["claim:line_items"])
        names = "; ".join(_name(i) for i in todo[:3])
        lead = (f"You haven't looked at {len(todo)} of {len(damaged)} damaged items." if SEEN
                else f"I have no gaze history yet, so all {len(damaged)} damaged items are not inspected.")
        return (f"{lead} Most urgent: {names}.", [f"manifest:{i.id}" for i in todo[:3]])

    if kind == "mold":
        molds = [i for i in items.values() if re.search(r"mou?ld", i.id + " " + i.label, re.I)]
        if not molds:
            return ("No mold is recorded in this house.", ["manifest"])
        where = "; ".join(_name(i) for i in molds)
        cov = {lines[i.id].coverage.value.replace("_", " ") for i in molds if i.id in lines}
        act = next((hazards[i.id].action for i in molds if i.id in hazards), "")
        act = act.split(".")[0] + "." if act else ""
        return (f"{len(molds)} mold area{'s' if len(molds) != 1 else ''}: {where}. {act} "
                f"Coverage: {', '.join(sorted(cov)) or 'not set'}.",
                [f"manifest:{i.id}" for i in molds])

    if kind == "contents":
        und = [i for i in items.values() if i.is_undamaged]
        named = [i for i in und if item_id == i.id] or und
        if not named:
            return None
        names = " and ".join(_safe(i.label, 45) for i in named)
        return (f"{names}: above the {wl:.1f} meter waterline and recorded as undamaged, so there is "
                f"nothing to cover. A claim for {'it' if len(named) == 1 else 'them'} gets flagged.",
                [f"manifest:{i.id}" for i in named])

    if kind == "drywall":
        from agents.pipeline import measure
        rs = measure.rooms()
        if not rs or fc is None:
            return None
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

    if kind == "waterline":
        if wl is None:
            return None
        msg = f"Water reached {wl:.2f} meters, about {wl * M_TO_IN:.0f} inches, on every wall."
        if fc is not None:
            msg += f" Drywall comes out to {fc:.1f} meters."
        return (msg, ["geometry:waterlineHeight"])

    if room:
        from agents.pipeline import measure
        rs = measure.rooms()
        label = rs.get(room, {}).get("label", room.replace("_", " ").title())
        if _SIZE_RX.search(text) and room in rs:
            r = rs[room]
            return (f"{label}: {r['floor_m2']:.1f} square meters of floor "
                    f"({r['floor_m2'] * M2_TO_FT2:,.0f} square feet), {r['flood_cut_m2']:.2f} square "
                    f"meters of flood cut.", [f"geometry:{room}"])
        in_room = [lines[i] for i, it in items.items()
                   if i in lines and (_room_of(it) == room
                                      or measure.rooms_for(i) == [room])]
        if not in_room:
            return (f"No damage is recorded in the {label.lower()}.", [f"geometry:{room}"])
        in_room.sort(key=lambda li: -items[li.item_id].severity)
        low = sum(li.estimate.low_usd for li in in_room)
        high = sum(li.estimate.high_usd for li in in_room)
        names = "; ".join(_name(items[li.item_id]) for li in in_room[:4])
        more = f" and {len(in_room) - 4} more" if len(in_room) > 4 else ""
        return (f"{label}: {len(in_room)} damaged items, {_usd(low)} to {_usd(high)} dollars. "
                f"Worst: {names}{more}.", [f"manifest:{li.item_id}" for li in in_room[:4]])
    return None


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


def _safe_label(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9 ,.'/()-]", "", str(text).replace("_", " "))[:60] or "an item"


def _answer(topic: str, item_id: str | None, draft: ClaimDraft | None,
            manifest: DamageManifest | None) -> tuple[str, list[str]]:
    """Template answer from structured data. Never LLM text."""
    if topic == "status":
        return ("This claim is a draft. Only the adjuster can approve it; no agent can.",
                ["claim:status"])
    if draft is None:
        return ("No assessment has run yet. Run the claim first.", [])
    li = next((x for x in draft.line_items if x.item_id == item_id), None)
    hz = next((h for h in draft.hazards if h.item_id == item_id), None)
    if topic == "measurement" or (item_id == "waterline_band"):
        wl = settings.waterline_m()
        return (f"Water reached {wl:.2f} meters.", ["geometry:waterlineHeight"])
    if item_id is None and topic == "hazard":
        # House-wide: the top hazards by priority, template text only.
        top = sorted(draft.hazards, key=lambda h: h.priority)[:3]
        if not top:
            return ("No safety hazards are recorded in this house.", ["claim:hazards"])
        names = {i.id: i.label for i in (manifest.items if manifest else [])}
        kinds = {"gas_co": "gas and carbon monoxide"}
        parts = [f"{_safe_label(names.get(h.item_id, h.item_id))}, "
                 f"{kinds.get(h.hazard_type, h.hazard_type.replace('_', ' '))}" for h in top]
        more = len(draft.hazards) - len(top)
        return (f"{len(draft.hazards)} hazard{'s' if len(draft.hazards) != 1 else ''}. "
                f"Most urgent: {'; '.join(parts)}." + (f" Plus {more} more." if more > 0 else ""),
                [f"hazard:{h.item_id}" for h in top])
    if item_id is None and topic == "coverage":
        c = {k: sum(1 for x in draft.line_items if x.coverage.value == k)
             for k in ("flood_policy", "homeowners_policy", "excluded", "needs_human")}
        return (f"{c['flood_policy']} items under the flood policy, {c['homeowners_policy']} under "
                f"homeowners, {c['excluded']} excluded, {c['needs_human']} need your review. "
                f"Look at an item for its reason.", ["claim:line_items"])
    if item_id is None:
        t = draft.totals
        if topic == "cost":
            return (f"The whole claim is estimated at {t.low_usd:,.0f} to {t.high_usd:,.0f} "
                    f"dollars.", ["claim:totals"])
        return (f"Look at an item and ask again. The whole claim is estimated at "
                f"{t.low_usd:,.0f} to {t.high_usd:,.0f} dollars.", ["claim:totals"])
    label = (li.label if li else item_id.replace("_", " "))[:60]
    if topic == "hazard" or (topic == "other" and hz and not li):
        if hz:
            return (f"{label}: priority {hz.priority} {hz.hazard_type.replace('_', ' ')} hazard. "
                    f"Dispatch {hz.dispatch.replace('_', ' ')}.", [f"hazard:{item_id}"])
        return (f"No hazard is recorded for {label}.", [f"manifest:{item_id}"])
    if li is None:
        it = next((i for i in (manifest.items if manifest else []) if i.id == item_id), None)
        if it is not None and it.is_undamaged:
            label = re.sub(r"[^A-Za-z0-9 ,.'/()-]", "", it.label)[:60] or label
            return (f"{label} is recorded as undamaged, so there is nothing to cover.",
                    [f"manifest:{item_id}"])
        return (f"There is no claim line for {label}.", [f"manifest:{item_id}"])
    if topic == "cost":
        return (f"{label}: estimated {li.estimate.low_usd:,.0f} to {li.estimate.high_usd:,.0f} "
                f"dollars from the rate table.", [f"costs:{item_id}"])
    cov = li.coverage.value.replace("_", " ")
    peril = li.peril.value.replace("_", " ")
    excl = f", exclusion {li.exclusion_ref}" if li.exclusion_ref else ""
    return (f"{label}: {peril}, {cov}{excl}.",
            [f"manifest:{item_id}"] + ([f"policy:{li.exclusion_ref}"] if li.exclusion_ref else []))


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
    # An item the adjuster names out loud beats the classifier's guess, which
    # beats gaze ("is the laptop damaged?" while looking at the router).
    item_id = _find_item(transcript, manifest, None) or cls["item_id"] or gaze
    is_question = cls["intent"] in ("question", "both") or bool(_Q.search(transcript))
    reply, cites = "", []
    if is_question:
        spec = _specific(transcript, item_id, draft, manifest)
        if spec is not None:
            reply, cites = spec
        else:
            reply, cites = _answer(cls["topic"], item_id, draft, manifest)
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
