"""Print the full raw response object from one NVIDIA chat call.

    python -m agents.tools.probe_raw intake "say ok"

Reasoning-tuned Nemotron models can put their answer in `reasoning_content`
and leave `content` empty, which silently looks like a dead model. This shows
exactly what came back so the client code is written against reality.
"""

from __future__ import annotations

import sys

from agents import settings
from agents.llm import _nvidia_client


def main() -> int:
    role = sys.argv[1] if len(sys.argv) > 1 else "intake"
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Reply with the single word: ok"
    model_id = settings.model(role)["id"]

    resp = _nvidia_client().chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.0,
    )
    choice = resp.choices[0]
    msg = choice.message

    print(f"model        : {model_id}")
    print(f"finish_reason: {choice.finish_reason}")
    print(f"usage        : {resp.usage}")
    print(f"content      : {msg.content!r}")
    for extra in ("reasoning_content", "reasoning", "thinking"):
        if hasattr(msg, extra):
            print(f"{extra:<13}: {getattr(msg, extra)!r}")
    if getattr(msg, "tool_calls", None):
        print(f"tool_calls   : {msg.tool_calls}")
    print("\nfull message dump:")
    print(msg.model_dump_json(indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
