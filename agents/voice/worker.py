"""LiveKit voice worker for room "floodvr": speech -> guard -> Voice Notes -> speech.

    python -m agents.voice.worker dev        # needs LIVEKIT_* + NVIDIA_API_KEY in agents/.env
                                             # and the API server on localhost:8000

Audio path (all NVIDIA-hosted, free developer credits, same NVIDIA_API_KEY):
  iPhone mic --LiveKit--> Riva Parakeet STT --> POST localhost:8000/voice
  (guard + Voice Notes agent, same code as the text fallback) --> Riva Magpie TTS
  --LiveKit--> iPhone speaker.

There is deliberately NO LiveKit LLM here: the spoken reply is whatever /voice
returns, which is a template over structured claim data. The full /voice JSON
(kind, proposals with proposal_id, guard findings) is also published on the
data channel, topic "floodvr.voice", so the phone can show "Confirm?" buttons;
confirmation goes to POST /voice/confirm, never through speech.

The phone may publish {"gaze_item_id": "..."} on topic "floodvr.gaze" so "is this
covered?" resolves to what the adjuster is looking at.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request

from agents import settings  # noqa: F401 - loads agents/.env into the environment

log = logging.getLogger("floodvr.voice")
API = os.getenv("FLOODVR_API", "http://localhost:8000")
TOPIC_REPLY = "floodvr.voice"
TOPIC_GAZE = "floodvr.gaze"


def _post_voice(transcript: str, gaze: str | None) -> dict:
    body = json.dumps({"transcript": transcript[:4000], "gaze_item_id": gaze}).encode()
    req = urllib.request.Request(f"{API}/voice", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed local URL
        return json.loads(r.read())


async def entrypoint(ctx) -> None:
    from livekit import rtc
    from livekit.agents import Agent, AgentSession
    from livekit.plugins import nvidia

    await ctx.connect()
    key = os.environ["NVIDIA_API_KEY"]
    session = AgentSession(stt=nvidia.STT(api_key=key), tts=nvidia.TTS(api_key=key))
    state: dict[str, str | None] = {"gaze": None}

    @ctx.room.on("data_received")
    def _on_data(pkt: rtc.DataPacket) -> None:
        if pkt.topic != TOPIC_GAZE:
            return
        try:
            gid = json.loads(pkt.data.decode()).get("gaze_item_id")
            state["gaze"] = gid if isinstance(gid, str) and len(gid) <= 80 else None
        except (ValueError, AttributeError):
            pass

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:
        if not getattr(ev, "is_final", False) or not ev.transcript.strip():
            return

        async def _reply() -> None:
            try:
                res = await asyncio.to_thread(_post_voice, ev.transcript, state["gaze"])
            except Exception as exc:  # noqa: BLE001 - keep the room alive
                log.warning("voice call failed: %s", exc)
                session.say("Sorry, the claim server didn't answer.")
                return
            await ctx.room.local_participant.publish_data(
                json.dumps(res).encode(), topic=TOPIC_REPLY, reliable=True)
            session.say(res.get("spoken_reply", "")[:300])

        asyncio.create_task(_reply())

    # An Agent with no LLM: replies come only from /voice via session.say().
    await session.start(room=ctx.room, agent=Agent(instructions="FloodVR voice relay"))
    session.say("FloodVR voice ready. Tap and ask.")


def main() -> None:
    from livekit.agents import WorkerOptions, cli
    missing = [k for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "NVIDIA_API_KEY")
               if not os.getenv(k)]
    if missing:
        raise SystemExit(f"missing in agents/.env: {', '.join(missing)}")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
