"""Tamper-evident audit log.

Each record stores sha256(prev_hash + canonical_body). Deleting or editing any
record breaks the chain from that point on, and `verify_chain()` says where.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.settings import AUDIT_PATH

GENESIS = "0" * 64


def _canonical(body: dict[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prev_hash: str, body: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical(body)).encode("utf-8")).hexdigest()


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    last = GENESIS
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line)["hash"]
                except (json.JSONDecodeError, KeyError):
                    continue
    return last


def append(run_id: str, step: str, body: dict[str, Any], path: Path | None = None) -> str:
    """Append one step. Returns the new chain head.

    Never pass secrets in `body` — this file is written to disk unencrypted.
    """
    path = path or AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = _last_hash(path)
    record_body = {
        "run_id": run_id,
        "step": step,
        "ts": datetime.now(timezone.utc).isoformat(),
        "body": body,
    }
    digest = _digest(prev, record_body)
    record = {**record_body, "prev": prev, "hash": digest}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return digest


def verify_chain(path: Path | None = None) -> tuple[bool, str]:
    """Walk the chain. Returns (ok, message naming the first bad line)."""
    path = path or AUDIT_PATH
    if not path.exists():
        return True, "no audit log yet"
    prev = GENESIS
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return False, f"line {lineno}: not valid JSON"
            body = {k: rec[k] for k in ("run_id", "step", "ts", "body") if k in rec}
            if rec.get("prev") != prev:
                return False, f"line {lineno}: prev hash does not match previous record"
            if _digest(prev, body) != rec.get("hash"):
                return False, f"line {lineno}: body was modified after it was written"
            prev = rec["hash"]
            count += 1
    return True, f"{count} records, chain intact"
