# Machine 3 (Windows) — AI + security status

Owner: AI + security workstream. Touches only `agents/`, `evals/`, `contracts/`,
`docs/STATUS-windows.md`. **Nothing under `Assets/` is modified.**

Last updated: 2026-11-07

---

## Working now (offline, no keys needed)

| Thing | Command | State |
|---|---|---|
| Offline pipeline | `python -m agents.tools.smoke` | 23 line items, 10 hazards, 5 needing human review |
| Eval suite | `python -m evals.run` | seed 39/39 caught, 0% false positives, 5/5 accuracy |
| API server | `python -m uvicorn agents.server:app --port 8000` | `/health`, `/manifest`, `/assess`, `/attack-demo`, `/results` |
| Public HTTPS | `cloudflared tunnel --url http://localhost:8000` | quick tunnel, no account |

`python -m evals.run` and `/assess` both work with **no API keys and no network**:
every model call falls back to a deterministic stub. The demo cannot be taken
down by the venue wi-fi.

## The one number that matters

Seed set: 39 attacks, 100% hijack with the guard off, **0% with it on**. That
number is not evidence — the same person wrote the attacks and the rules.

Held-out set: **not generated yet.** `python -m evals.gen_variants` has Claude
write fresh attacks, and `python -m evals.run` measures them *before any rule is
touched*. Both numbers go in the report; judges see the honest one.

## Blocked on keys

Nothing live has run yet. `agents/llm.py` has never made a real network call,
and the NVIDIA model ids in `agents/config.yaml` are marked `unverified`.

Needs `agents/.env` (gitignored, never printed or committed):
- `NVIDIA_API_KEY` — build.nvidia.com, free developer credits, $0
- `ANTHROPIC_API_KEY` — console.anthropic.com, pay-as-you-go. Set a $20 limit.

Then:
```
python -m agents.tools.verify_models --probe-guard
python -m evals.gen_variants
python -m evals.run --guard-model
```

## Contract with the Unity machines

- `contracts/damage_manifest.schema.json` matches `Assets/Scripts/DamageItem.cs`
  field for field. If Mac 1 adds a field, update the schema, not the C#.
- `contracts/samples/house_manifest.json` is generated from the real Unity export
  by `python -m agents.tools.make_sample_manifest`. It refuses to overwrite an
  existing file — if Mac 1 pushes their own, theirs wins.
- `contracts/claim_draft.schema.json` is what `/assess` returns.
- Still needed from Mac 1 or Mac 2: **one VR screenshot with the fridge note
  visible**, for the vision path. Drop it in `contracts/samples/screenshots/`.

## Design decisions worth knowing

- The orchestrator never sees raw untrusted text. Intake runs in quarantine with
  no tools and can only return a schema-validated `ExtractedEvidence`.
- Costs come only from `contracts/costs.json` and are clamped per line item and
  per claim. Even a fully hijacked pipeline cannot emit an arbitrary payout.
- `status` on a claim draft is a constant `draft_pending_human`. There is no code
  path that approves payment.
- `agents/audit.jsonl` is hash-chained; `/health` reports whether it is intact.
- The policy in `contracts/policy.json` is synthetic. Swap it if State Farm hands
  out real sample language at the event.
