"""FastAPI surface for the VR app and the adjuster console.

    uvicorn agents.server:app --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from agents import audit, guard, settings
from agents.llm import LLMUnavailable, vision_read
from agents.pipeline.orchestrator import assess
from agents.schemas import (
    AssessRequest, AttackDemoRequest, Channel, ClaimDraft, DamageManifest,
)

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
    try:
        if planner == "llm":
            from agents.pipeline.planner import assess_planned
            draft = assess_planned(req)
        else:
            draft = assess(req)
        if report:
            from agents.pipeline.writer import write
            untrusted = {f"evidence:{d.doc_id}": d.text for d in req.evidence}
            untrusted.update({f"scene_text:{s.id}": s.text for s in req.manifest.scene_text})
            draft.adjuster_report = write(draft, untrusted)
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
            "text": text,
            "ocr_used": ocr_used,
            "vlm_model": vlm_model,
            "channel": channel.value,
        },
        "detected": blocked,
        "findings": [f.model_dump(mode="json") for f in findings],
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


@app.get("/vision")
def vision() -> dict:
    """Vision Inspector result (Nemotron VL vs screens.json), from the cache that
    `python -m agents.pipeline.vision` writes. Never runs 9 VLM calls per request."""
    from agents.pipeline.vision import cached
    data = cached()
    if not data:
        raise HTTPException(404, "no vision run yet — run `python -m agents.pipeline.vision`")
    return data


@app.get("/results")
def results() -> dict:
    """Latest eval numbers, for the console. Written by `python -m evals.run`."""
    path = settings.EVALS_DIR / "results.json"
    if not path.exists():
        raise HTTPException(404, "no eval results yet — run `python -m evals.run`")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/")
def console() -> FileResponse:
    index = CONSOLE_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "console not built yet")
    return FileResponse(index)
