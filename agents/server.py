"""FastAPI surface for the VR app and the adjuster console.

    uvicorn agents.server:app --port 8000
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from pydantic import BaseModel, ConfigDict, Field

from agents import audit, guard, output_guard, settings
from agents.llm import LLMUnavailable, vision_read
from agents.pipeline.orchestrator import assess
from agents.schemas import (
    AssessRequest, AttackDemoRequest, Channel, ClaimDraft, DamageManifest,
)

ASSESS_BUDGET_S = 55.0  # whole /assess, well under the tunnel's 100 s cutoff

app = FastAPI(
    title="FloodVR claim agents",
    version="0.1.0",
    description="Agentic flood-claim assessment with prompt-injection defence.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONSOLE_DIR = settings.AGENTS_DIR / "console"
SAMPLE_MANIFEST = settings.CONTRACTS_DIR / "samples" / "house_manifest.json"


@app.get("/health")
def health() -> dict:
    ok, msg = audit.verify_chain()
    return {
        "status": "ok",
        "offline": settings.is_offline(),
        "nvidia_key": settings.has_key("nvidia"),
        "anthropic_key": settings.has_key("anthropic"),
        "models": {k: v["id"] for k, v in settings.config()["models"].items()},
        "audit_chain": {"intact": ok, "detail": msg},
    }


@app.get("/manifest")
def manifest() -> dict:
    """The sample manifest, so the VR app and console share one source."""
    if not SAMPLE_MANIFEST.exists():
        raise HTTPException(404, "sample manifest not generated yet")
    return json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))


@app.post("/assess", response_model=ClaimDraft)
def assess_endpoint(req: AssessRequest, planner: str = "llm", report: bool = True) -> ClaimDraft:
    """`planner=llm` (default): Nemotron orders the stages with tool calls.
    `planner=fixed`: fixed order. The claim is identical; only the trace differs.
    `report=true` (default): the Claim Writer adds `adjuster_report` (number-checked)."""
    # Hard time budget for the whole request (Cloudflare cuts the tunnel at 100 s):
    # the planner gets PLANNER_BUDGET_S, the writer whatever is left of
    # ASSESS_BUDGET_S, then falls back to its template. The claim never changes.
    t_start = time.perf_counter()
    try:
        if planner == "llm":
            from agents.pipeline.planner import PLANNER_BUDGET_S, assess_planned
            draft = assess_planned(req, budget_s=PLANNER_BUDGET_S)
        else:
            draft = assess(req)
        if report:
            from agents.pipeline.writer import write
            untrusted = {f"evidence:{d.doc_id}": d.text for d in req.evidence}
            untrusted.update({f"scene_text:{s.id}": s.text for s in req.manifest.scene_text})
            draft.adjuster_report = write(draft, untrusted, deadline=t_start + ASSESS_BUDGET_S)
        if req.guard_enabled:
            _LAST.update(draft=draft, manifest=req.manifest)  # headset shows the latest run
        return draft
    except LLMUnavailable as exc:
        raise HTTPException(503, f"model unavailable: {exc}") from exc


@app.post("/attack-demo")
def attack_demo(req: AttackDemoRequest) -> JSONResponse:
    """Run one attack guarded vs unguarded, side by side.

    Accepts raw text, or a base64 VR screenshot which is OCR'd by the Nemotron
    VLM first. The VLM's output is UNTRUSTED and goes through the same guard.
    """
    text = req.text
    ocr_used = False
    vlm_model = None

    if req.image_b64:
        try:
            comp = vision_read(req.image_b64)
            text = comp.text
            ocr_used = True
            vlm_model = comp.model
        except LLMUnavailable as exc:
            raise HTTPException(503, f"vision model unavailable: {exc}") from exc

    if not text.strip():
        raise HTTPException(400, "provide `text` or `image_b64`")

    channel = Channel.vlm_output if ocr_used else req.channel
    blocked, findings = guard.inspect(text, source="attack-demo", channel=channel)

    manifest_data = (
        json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))
        if SAMPLE_MANIFEST.exists() else {"items": []}
    )
    parsed = DamageManifest.model_validate(manifest_data)

    guarded = assess(AssessRequest(
        manifest=parsed.model_copy(deep=True),
        evidence=[{"doc_id": "attack", "channel": channel, "text": text}],
        guard_enabled=True,
    ))
    unguarded = assess(AssessRequest(
        manifest=parsed.model_copy(deep=True),
        evidence=[{"doc_id": "attack", "channel": channel, "text": text}],
        guard_enabled=False,
    ))

    return JSONResponse({
        "input": {
            "text": output_guard.sanitise_text(text)[0],
            "ocr_used": ocr_used,
            "vlm_model": vlm_model,
            "channel": channel.value,
        },
        "detected": blocked,
        "findings": [{**f.model_dump(mode="json"),
                      "snippet": output_guard.sanitise_text(f.snippet)[0]} for f in findings],
        "guarded": {
            "reached_privileged_zone": False if blocked else True,
            "security_findings": len(guarded.security_findings),
            "totals": guarded.totals.model_dump(mode="json"),
            "audit_trail_id": guarded.audit_trail_id,
        },
        "unguarded": {
            "reached_privileged_zone": True,
            "security_findings": len(unguarded.security_findings),
            "totals": unguarded.totals.model_dump(mode="json"),
            "audit_trail_id": unguarded.audit_trail_id,
        },
    })


_LAST: dict = {"draft": None, "manifest": None, "baseline_key": None}


def _baseline() -> tuple[ClaimDraft, DamageManifest]:
    """Fixed-order run on Mac 1's sample manifest, cached until the file changes.
    No evidence, so no LLM call: fast and identical across polls."""
    key = SAMPLE_MANIFEST.stat().st_mtime if SAMPLE_MANIFEST.exists() else None
    if _LAST.get("baseline_key") != key or _LAST.get("baseline") is None:
        data = (json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))
                if SAMPLE_MANIFEST.exists() else {"items": []})
        m = DamageManifest.model_validate(data)
        _LAST["baseline"] = (assess(AssessRequest(manifest=m.model_copy(deep=True))), m)
        _LAST["baseline_key"] = key
    return _LAST["baseline"]


@app.get("/callouts")
def callouts(seen: str = "") -> dict:
    """Headset callouts (contracts/callouts.schema.json) for the latest guarded /assess
    run, or a cached baseline run. Same bytes on every poll until a new run happens.
    `?seen=id1,id2` drops callouts (by callout id or item id) the adjuster has seen."""
    from agents.pipeline.callouts import build
    if _LAST["draft"] is not None:
        draft, manifest = _LAST["draft"], _LAST["manifest"]
    else:
        draft, manifest = _baseline()
    return build(draft, manifest, {s for s in seen.split(",") if s})


class VoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(max_length=4000)
    standpoint: str | None = Field(default=None, max_length=80)
    gaze_item_id: str | None = Field(default=None, max_length=80)
    audit_trail_id: str | None = Field(default=None, max_length=80)


class VoiceConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: str = Field(max_length=40)
    accept: bool


@app.post("/voice")
def voice(req: VoiceRequest) -> dict:
    """Text path for voice (Safari speech recognition fallback; the LiveKit worker
    uses the same function). contracts/voice.schema.json. The transcript is
    UNTRUSTED; updates are proposals that need POST /voice/confirm."""
    from agents.voice import notes
    if _LAST["draft"] is not None:
        draft, manifest = _LAST["draft"], _LAST["manifest"]
    else:
        draft, manifest = _baseline()
    return notes.handle(req.transcript, gaze_item_id=req.gaze_item_id,
                        standpoint=req.standpoint, audit_trail_id=req.audit_trail_id,
                        draft=draft, manifest=manifest)


@app.post("/voice/confirm")
def voice_confirm(req: VoiceConfirm) -> dict:
    """The adjuster accepts or rejects one proposed voice update."""
    from agents.voice import notes
    res = notes.confirm(req.proposal_id, req.accept)
    if not res["ok"]:
        raise HTTPException(404 if "unknown" in res["error"] else 409, res["error"])
    return res


@app.get("/voice/pending")
def voice_pending() -> dict:
    from agents.voice import notes
    return {"proposals": list(notes.PENDING.values())}


@app.post("/voice/token")
def voice_token() -> dict:
    """LiveKit join token for the iPhone (room `floodvr`). 503 until LIVEKIT_* are set."""
    from agents.voice import token
    if not token.configured():
        raise HTTPException(503, "LiveKit not configured on the server; use POST /voice (text) instead")
    out = token.mint()
    out["agent"] = token.ensure_agent(out["room"])
    return out


@app.post("/voice/agent")
def voice_agent() -> dict:
    """Ask for the voice agent again if it has not joined (the client calls this
    when it waits too long, e.g. right after the worker restarted)."""
    from agents.voice import token
    if not token.configured():
        raise HTTPException(503, "LiveKit not configured on the server")
    return {"agent": token.ensure_agent(token.ROOM)}


@app.get("/measurements")
def measurements() -> dict:
    """Room quantities recomputed from house_geometry.json + cross-check vs Mac 1's export."""
    from agents.pipeline import measure
    s = measure.summary()
    if not s["rooms"]:
        raise HTTPException(404, "house_geometry.json not present")
    return s


@app.get("/vision")
def vision() -> dict:
    """Vision Inspector result (Nemotron VL vs screens.json), from the cache that
    `python -m agents.pipeline.vision` writes. Never runs 9 VLM calls per request."""
    from agents.pipeline.vision import cached
    data = cached()
    if not data:
        raise HTTPException(404, "no vision run yet — run `python -m agents.pipeline.vision`")
    from agents import output_guard
    for img in data["images"]:  # VLM output is untrusted: scrub before it leaves
        img["transcribed_text"] = [output_guard.sanitise_text(t)[0] for t in img["transcribed_text"]]
        for f in img["security_findings"]:
            f["snippet"] = output_guard.sanitise_text(f["snippet"])[0]
    return data


@app.get("/results")
def results() -> dict:
    """Latest eval numbers, for the console. Written by `python -m evals.run`."""
    path = settings.EVALS_DIR / "results.json"
    if not path.exists():
        raise HTTPException(404, "no eval results yet — run `python -m evals.run`")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Missed attacks and flagged clean docs are raw evidence text: scrub before output.
    for st in data.get("sets", {}).values():
        for m in st.get("missed_attacks", []):
            m["text"] = output_guard.sanitise_text(m.get("text", ""))[0]
    for fp in data.get("clean", {}).get("flagged", []):
        fp["text"] = output_guard.sanitise_text(fp.get("text", ""))[0]
    return data


@app.get("/")
@app.get("/console")
def console() -> FileResponse:
    index = CONSOLE_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "console not built yet")
    return FileResponse(index)


@app.get("/voice/client.js")
def voice_client() -> FileResponse:
    """Browser/WebGL LiveKit voice client (window.FloodVRVoice). The headset's
    jslib loads this, so it can be fixed here without rebuilding the app."""
    return FileResponse(CONSOLE_DIR / "floodvr-voice.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/voice-test")
def voice_test() -> FileResponse:
    """Phone test page: open on the iPhone, tap Connect, hold to talk."""
    return FileResponse(CONSOLE_DIR / "voice.html")


SCREENS_DIR = settings.CONTRACTS_DIR / "samples" / "screens"


@app.get("/screens/{name}")
def screen(name: str) -> FileResponse:
    """VR screenshots for the console's vision panel. Names are checked against
    screens.json, so no path from the request ever reaches the filesystem."""
    key = json.loads((SCREENS_DIR / "screens.json").read_text(encoding="utf-8"))["screens"]
    allowed = {s["filename"] for s in key}
    if name not in allowed:
        raise HTTPException(404, "unknown screenshot")
    return FileResponse(SCREENS_DIR / name, media_type="image/png")
