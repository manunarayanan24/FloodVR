"""LiveKit access tokens for the iPhone, minted locally (HS256 JWT, stdlib only).

Needs LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in agents/.env (never
printed). The token lets one adjuster join room ROOM, publish their mic and
hear the agent's reply; nothing else.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

ROOM = "floodvr"
TTL_S = 3600
# The worker registers under this name. LiveKit Cloud does not reliably
# auto-dispatch unnamed agents, so every join token asks for this one.
AGENT_NAME = "floodvr-voice"


def configured() -> bool:
    return all(os.getenv(k) for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint(identity: str | None = None, room: str = ROOM) -> dict:
    key, secret = os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"]
    identity = identity or f"adjuster-{secrets.token_hex(3)}"
    now = int(time.time())
    claims = {
        "iss": key, "sub": identity, "nbf": now - 10, "exp": now + TTL_S,
        "name": identity,
        "video": {"room": room, "roomJoin": True, "canPublish": True,
                  "canSubscribe": True, "canPublishData": True},
        # Dispatch the voice agent when this participant creates the room.
        "roomConfig": {"agents": [{"agentName": AGENT_NAME}]},
    }
    return {"url": os.environ["LIVEKIT_URL"], "token": _sign(claims, secret),
            "room": room, "identity": identity, "expires_in_s": TTL_S}


def _sign(claims: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}." \
              f"{_b64(json.dumps(claims, separators=(',', ':')).encode())}"
    sig = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64(sig)}"


def _twirp(service: str, method: str, body: dict, video: dict) -> dict:
    """Call a LiveKit server API with a short-lived admin token (stdlib only)."""
    import urllib.request

    key, secret = os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"]
    now = int(time.time())
    jwt = _sign({"iss": key, "sub": "floodvr-server", "nbf": now - 10, "exp": now + 60,
                 "video": video}, secret)
    url = os.environ["LIVEKIT_URL"].replace("wss://", "https://", 1)
    req = urllib.request.Request(
        f"{url}/twirp/livekit.{service}/{method}", data=json.dumps(body).encode(),
        method="POST", headers={"Authorization": f"Bearer {jwt}",
                                "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - our LiveKit project
        return json.loads(r.read() or b"{}")


STARTING_S = 90  # a dispatch younger than this, not yet finished, counts as "agent starting"


def _dispatch_starting(room: str, admin: dict) -> bool:
    """True if our agent was dispatched to this room recently and has not finished."""
    try:
        d = _twirp("AgentDispatchService", "ListDispatch", {"room": room}, admin)
    except Exception:  # noqa: BLE001 - unknown: treat as not starting
        return False
    now_ns = time.time_ns()
    for x in d.get("agent_dispatches", d.get("agentDispatches", [])):
        if x.get("agent_name", x.get("agentName")) != AGENT_NAME:
            continue
        st = x.get("state", {})
        created = int(st.get("created_at", st.get("createdAt")) or 0)
        age_s = (now_ns - created) / 1e9 if created else 1e9
        if age_s > STARTING_S:
            continue
        jobs = st.get("jobs", [])
        if not jobs or any(str(j.get("state", {}).get("status", "")) in ("JS_PENDING", "JS_RUNNING")
                           for j in jobs):
            return True
    return False


def ensure_agent(room: str = ROOM) -> str:
    """If the room already exists (roomConfig only fires on creation), make sure
    our agent is dispatched to it. Returns what happened; never raises."""
    admin = {"roomAdmin": True, "room": room, "roomList": True}
    try:
        rooms = _twirp("RoomService", "ListRooms", {"names": [room]}, admin).get("rooms", [])
        if not rooms:
            return "room will be created on join (agent via roomConfig)"
        # Check who is actually in the room, not dispatch records (a finished
        # job can leave a stale record behind).
        try:
            parts = _twirp("RoomService", "ListParticipants", {"room": room}, admin)
            if any(str(p.get("kind", "")).upper() in ("AGENT", "4")
                   for p in parts.get("participants", [])):
                return "agent already in room"
        except Exception:  # noqa: BLE001 - room may be mid-teardown; dispatch anyway
            pass
        # An agent that was dispatched a moment ago has not joined yet: a second
        # dispatch here (another phone, or the client's retry) would put TWO agents
        # in the room and every answer would be spoken twice.
        if _dispatch_starting(room, admin):
            return "agent is starting"
        _twirp("AgentDispatchService", "CreateDispatch",
               {"room": room, "agent_name": AGENT_NAME}, admin)
        return "agent dispatched to existing room"
    except Exception as exc:  # noqa: BLE001 - a token must still be issued
        return f"dispatch check failed: {type(exc).__name__}"
