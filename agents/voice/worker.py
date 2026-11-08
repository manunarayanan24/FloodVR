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
import re
import logging
import os
import time
import urllib.request
from typing import Any

from agents import settings  # noqa: F401 - loads agents/.env into the environment

# LiveKit plugins must be registered on the main thread, i.e. at import time,
# not inside the job entrypoint (that crashes the job). Optional so the rest of
# the repo imports without the voice extras installed.
try:
    from livekit.plugins import nvidia  # noqa: E402
except ImportError:  # pragma: no cover - voice extras not installed
    nvidia = None

log = logging.getLogger("floodvr.voice")
API = os.getenv("FLOODVR_API", "http://localhost:8000")
TOPIC_REPLY = "floodvr.voice"
TOPIC_GAZE = "floodvr.gaze"
TOPIC_HEARD = "floodvr.heard"
TOPIC_PTT = "floodvr.ptt"
MERGE_PAUSE_S = 2.0    # open mic: answer this long after the adjuster stops talking
ECHO_TAIL_S = 1.0      # ignore speech heard this soon after the agent stops speaking
RELEASE_GRACE_S = 1.5  # after the button is released: let the last words arrive


def _post_voice(transcript: str, gaze: str | None, seen: list[str] | None = None) -> dict:
    body = json.dumps({"transcript": transcript[:4000], "gaze_item_id": gaze,
                       "seen_item_ids": (seen or [])[-200:]}).encode()
    req = urllib.request.Request(f"{API}/voice", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed local URL
        return json.loads(r.read())


async def entrypoint(ctx) -> None:
    from livekit import rtc
    from livekit.agents import Agent, AgentSession

    await ctx.connect()
    key = os.environ["NVIDIA_API_KEY"]
    session = AgentSession(stt=nvidia.STT(api_key=key), tts=nvidia.TTS(api_key=key))
    state: dict[str, str | None] = {"gaze": None}
    seen: list[str] = []  # every item looked at this session, for "what did I miss?"

    @ctx.room.on("data_received")
    def _on_data(pkt: rtc.DataPacket) -> None:
        if pkt.topic == TOPIC_PTT:
            try:
                s = json.loads(pkt.data.decode()).get("state")
            except (ValueError, AttributeError):
                return
            if s in ("pressed", "released"):
                _on_ptt(s)
            return
        if pkt.topic != TOPIC_GAZE:
            return
        try:
            gid = json.loads(pkt.data.decode()).get("gaze_item_id")
            state["gaze"] = gid if isinstance(gid, str) and len(gid) <= 80 else None
            if state["gaze"] and state["gaze"] not in seen:
                seen.append(state["gaze"])
        except (ValueError, AttributeError):
            pass

    # Listen to whoever is talking. By default RoomIO links to the FIRST
    # participant forever, so a phone joining after a test client (or after a
    # reconnect under a new identity) was silently ignored.
    def _is_person(p) -> bool:
        return p is not None and p.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT

    def _link(p, why: str) -> None:
        rio = session.room_io
        if rio is None or not _is_person(p):
            return
        current = rio.linked_participant
        if current is None or current.identity != p.identity:
            log.info("voice: listening to %s (%s)", p.identity, why)
            rio.set_participant(p.identity)

    @ctx.room.on("track_subscribed")
    def _on_track(track, pub, participant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            _link(participant, "published mic")

    @ctx.room.on("track_unmuted")
    def _on_unmute(participant, pub) -> None:
        if pub.kind == rtc.TrackKind.KIND_AUDIO:
            _link(participant, "unmuted mic")

    @ctx.room.on("participant_disconnected")
    def _on_left(participant) -> None:
        rio = session.room_io
        if rio is None or rio.linked_participant is None:
            return
        if rio.linked_participant.identity == participant.identity:
            others = [p for p in ctx.room.remote_participants.values()
                      if _is_person(p) and p.identity != participant.identity]
            if others:
                _link(others[-1], "previous speaker left")
            else:
                rio.unset_participant()  # re-links to the next person who joins

    # Speech-to-text emits several final pieces for one question ("Hey man." /
    # "do you sense any hazards?"). Collect pieces and answer once, after a
    # short pause, so the adjuster gets one reply per question.
    # Push-to-talk clients send floodvr.ptt pressed/released: while held we only
    # collect; on release we answer RELEASE_GRACE_S later (late pieces still
    # land). Clients without that signal get a MERGE_PAUSE_S pause instead.
    pending: dict[str, Any] = {"parts": [], "task": None, "mode": "idle"}

    def _schedule(delay: float) -> None:
        if pending["task"] is not None:
            pending["task"].cancel()
        pending["task"] = asyncio.create_task(_flush_after(delay))

    async def _flush_after(delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        pending["task"], pending["mode"] = None, "idle"
        if not pending["parts"]:
            return
        text = " ".join(pending["parts"])[:4000]
        pending["parts"] = []
        await _reply(text)

    # Open mic: the phone speaker plays our reply and the mic can pick it up.
    # Ignore anything heard while the agent is speaking (and briefly after), or
    # that mostly repeats our last reply. Echo cancellation should catch it
    # first; this is the backstop so the agent never answers itself.
    echo: dict[str, Any] = {"speaking": False, "quiet_at": 0.0, "last_reply": ""}

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        if ev.new_state == "speaking":
            echo["speaking"] = True
        elif ev.old_state == "speaking":
            echo["speaking"], echo["quiet_at"] = False, time.monotonic()

    def _is_echo(text: str) -> bool:
        if echo["speaking"] or time.monotonic() - echo["quiet_at"] < ECHO_TAIL_S:
            return True
        said = set(re.findall(r"[a-z0-9]+", echo["last_reply"].lower()))
        heard = re.findall(r"[a-z0-9]+", text.lower())
        return len(heard) >= 3 and sum(w in said for w in heard) / len(heard) >= 0.7

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        # Open mic: wait while the adjuster is still talking, answer after a pause.
        if pending["mode"] != "idle":
            return
        if ev.new_state == "speaking" and pending["task"] is not None:
            pending["task"].cancel()
            pending["task"] = None
        elif ev.new_state == "listening" and pending["parts"]:
            _schedule(MERGE_PAUSE_S)

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:
        if not getattr(ev, "is_final", False) or not ev.transcript.strip():
            return
        if _is_echo(ev.transcript):
            log.info("voice: ignored (sounded like our own reply)")
            return
        pending["parts"].append(ev.transcript.strip())
        if pending["mode"] == "idle":  # open mic / no push-to-talk signal: pause-based
            _schedule(MERGE_PAUSE_S)

    def _on_ptt(state_name: str) -> None:
        if state_name == "pressed":
            pending["mode"] = "held"
            if pending["task"] is not None:
                pending["task"].cancel()
                pending["task"] = None
        elif state_name == "released":
            pending["mode"] = "release"
            _schedule(RELEASE_GRACE_S)

    async def _reply(transcript: str) -> None:
            # What the agent heard, for the headset's caption (topic floodvr.heard).
            from agents import output_guard
            heard, _ = output_guard.sanitise_text(transcript[:500])
            await ctx.room.local_participant.publish_data(
                heard.encode(), topic=TOPIC_HEARD, reliable=True)
            try:
                res = await asyncio.to_thread(_post_voice, transcript, state["gaze"], list(seen))
            except Exception as exc:  # noqa: BLE001 - keep the room alive
                log.warning("voice call failed: %s", exc)
                session.say("Sorry, the claim server didn't answer.", allow_interruptions=False)
                return
            await ctx.room.local_participant.publish_data(
                json.dumps(res).encode(), topic=TOPIC_REPLY, reliable=True)
            reply = res.get("spoken_reply", "")[:300]
            echo["last_reply"] = reply
            # Not interruptible: in open mic our own voice must not cut us off.
            session.say(reply, allow_interruptions=False)

    # An Agent with no LLM: replies come only from /voice via session.say().
    # close_on_disconnect=False: if the phone drops and rejoins, the agent is
    # still in the room. The job ends when LiveKit closes the empty room.
    from livekit.agents.voice import room_io
    await session.start(room=ctx.room, agent=Agent(instructions="FloodVR voice relay"),
                        room_options=room_io.RoomOptions(close_on_disconnect=False))
    # Two agents in one room would answer every question twice. If another agent
    # is here and sorts before us, leave (exactly one of any pair leaves).
    await asyncio.sleep(2.5)
    me = ctx.room.local_participant.identity
    older = [p for p in ctx.room.remote_participants.values()
             if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT and p.identity < me]
    if older:
        log.info("voice: duplicate agent (%s is already here); leaving", older[0].identity)
        ctx.shutdown(reason="duplicate agent")
        return
    echo["last_reply"] = "FloodVR voice ready. Ask me anything."
    session.say(echo["last_reply"], allow_interruptions=False)


def main() -> None:
    from livekit.agents import WorkerOptions, cli
    missing = [k for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "NVIDIA_API_KEY")
               if not os.getenv(k)]
    if missing:
        raise SystemExit(f"missing in agents/.env: {', '.join(missing)}")
    if nvidia is None:
        raise SystemExit("pip install -r agents/voice/requirements.txt")
    from agents.voice.token import AGENT_NAME
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))


if __name__ == "__main__":
    main()
