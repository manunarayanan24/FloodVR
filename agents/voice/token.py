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
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}." \
              f"{_b64(json.dumps(claims, separators=(',', ':')).encode())}"
    sig = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return {"url": os.environ["LIVEKIT_URL"], "token": f"{signing}.{_b64(sig)}",
            "room": room, "identity": identity, "expires_in_s": TTL_S}
