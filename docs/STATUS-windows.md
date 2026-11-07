# Machine 3 (Windows) — AI + security status

Owner: Abhinav. Lane: `agents/`, `evals/`, `contracts/` **except
`contracts/samples/`**, `docs/STATUS-windows.md`. **Nothing under `Assets/` is
modified.**

Last updated: 2026-11-07

---

## Live API (current)

**Base URL:** `https://operates-voters-officials-lenses.trycloudflare.com`

> Quick tunnels die when `cloudflared` stops. This URL is valid only while the
> Windows box is up — check here after any restart. Read it at runtime (`?api=`),
> never bake it into a build.

| Method | Path | State | Returns |
|---|---|---|---|
| `GET` | `/health` | live | offline flag, key presence, model ids, audit-chain status |
| `GET` | `/manifest` | live | Mac 1's `contracts/samples/house_manifest.json` |
| `POST` | `/assess` | live | claim draft (`contracts/claim_draft.schema.json`) |
| `POST` | `/attack-demo` | live | one attack, guarded vs unguarded, side by side |
| `GET` | `/results` | live | latest eval numbers (`evals/results.json`) |
| `GET` | `/callouts` | **schema only** | `contracts/callouts.schema.json` — not implemented yet |
| `POST` | `/voice` | **schema only** | `contracts/voice.schema.json` — not implemented yet |

CORS allows `https://*.vercel.app` and `http://localhost:<port>`.

Quick check from any machine:
```bash
curl https://operates-voters-officials-lenses.trycloudflare.com/health
```

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

## Live NVIDIA findings (worth knowing on the other machines)

We are live on NVIDIA. First real network calls this project has made, and four
things broke that would have broken on stage:

1. **Every model id in `config.yaml` was dead** — 404 or 410. The ids in the
   original brief do not exist on the hosted API. Working ids are now pinned in
   `agents/config.yaml` with verified fallbacks.
2. **`GET /models` listing a model does not mean you can call it.**
   `nvidia/nemotron-3-super-120b-a12b` is listed and still 404s on chat
   completions. Always probe, never trust the listing.
3. **Nemotron 3.5 models are reasoning-tuned.** They spend the token budget on
   `reasoning_content` before writing `content`. With a small `max_tokens` you
   get an empty string and `finish_reason: "stop"` — indistinguishable from a
   dead model. There is now a 512-token floor.
4. **The endpoint answers bursts with HTTP 403**, not 429. Throttling and
   backoff added.

**The guard model does not detect injection.** Verified against a real raw
reply: `{"User Safety": "safe"}` for our live fridge-note attack. NVIDIA's
content-safety models catch harmful *content* (violence, hate), which is a
different problem. The verdict parser is correct; the model is the wrong tool.
The second layer is **disabled** until the bake-off finds a candidate that earns
it. We will report whichever way it lands rather than claim a layer that does
nothing.

## Still blocked

- `ANTHROPIC_API_KEY` is **not set** in `agents/.env`. Held-out attack
  generation (`python -m evals.gen_variants`, ~20 cents) cannot run, so the only
  attack numbers we have are the optimistic ones.
- **`screens.json` answer key** from Mac 1 — the Vision Inspector cannot be
  scored without it. The 9 PNGs have landed.
- **Contents items with `heightAboveFloor` and `severity: 0`** from Mac 1 — the
  fraud-checker trap. Schema and pipeline already handle both; there is just no
  data to exercise them yet.

## Contract with the Unity machines

- `contracts/damage_manifest.schema.json` tracks `DamageItem.cs`, now including
  `severity: 0` and `heightAboveFloor`. If Mac 1 adds a field, the schema
  changes, not the C#.
- `contracts/samples/` is **Mac 1's lane and is never written from Windows.**
  `python -m agents.tools.make_sample_manifest` writes
  `contracts/fixtures/house_manifest.windows.json` instead, used only as a
  fallback when Mac 1's sample is missing.
- `contracts/claim_draft.schema.json` is what `/assess` returns.
- `contracts/callouts.schema.json` and `contracts/voice.schema.json` are
  **proposals for Mac 2** — comment before building against them.

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
