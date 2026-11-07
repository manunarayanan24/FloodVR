"""Configuration loading. All paths are pathlib; no model id is hardcoded."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO_ROOT / "agents"
CONTRACTS_DIR = REPO_ROOT / "contracts"
EVALS_DIR = REPO_ROOT / "evals"

CONFIG_PATH = AGENTS_DIR / "config.yaml"
ENV_PATH = AGENTS_DIR / ".env"
AUDIT_PATH = AGENTS_DIR / "audit.jsonl"

load_dotenv(ENV_PATH, override=False)


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def policy() -> dict[str, Any]:
    return json.loads((REPO_ROOT / config()["policy"]["file"]).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def costs() -> dict[str, Any]:
    return json.loads((REPO_ROOT / config()["policy"]["costs_file"]).read_text(encoding="utf-8"))


def waterline_m() -> float:
    return float(config()["policy"]["waterline_m"])


def is_offline() -> bool:
    """Offline mode uses deterministic stubs: no network, no keys required.

    An explicit FLOODVR_OFFLINE env var always wins over config.yaml, so the
    eval suite can be forced offline in CI and live at the demo.
    """
    raw = os.getenv("FLOODVR_OFFLINE")
    if raw is not None:
        return raw.strip() not in {"0", "false", "False", ""}
    return bool(config()["runtime"]["offline"])


def model(name: str) -> dict[str, Any]:
    """Model entry by logical name, e.g. 'orchestrator'."""
    try:
        return config()["models"][name]
    except KeyError as exc:  # pragma: no cover - configuration error
        raise KeyError(f"No model '{name}' in {CONFIG_PATH.name}") from exc


def api_key(provider: str) -> str | None:
    """Return the key for a provider, or None. The value is never logged."""
    env_name = config()["providers"][provider]["api_key_env"]
    value = os.getenv(env_name, "").strip()
    return value or None


def has_key(provider: str) -> bool:
    key = api_key(provider)
    return bool(key) and "REPLACE_ME" not in key
