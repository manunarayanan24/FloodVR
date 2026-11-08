# Machine 3 (Windows) — AI + security status

**Tunnel (live): https://starter-king-jackson-avon.trycloudflare.com** — `/health` ok, live NVIDIA, audit chain intact.

Owner: Abhinav. Lane: `agents/`, `evals/`, `contracts/` **except
`contracts/samples/`**, `docs/STATUS-windows.md`. **Nothing under `Assets/` is
modified.**

Last updated: 2026-11-07 (new account session; tunnel restarted)

---

## Live API (current)

**Base URL:** `https://starter-king-jackson-avon.trycloudflare.com`

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
curl https://starter-king-jackson-avon.trycloudflare.com/health
```

---

## Working now

| Thing | Command | State |
|---|---|---|
| Pipeline | `python -m agents.tools.smoke` | 26 manifest items → 24 claimable line items, 10 hazards, 5 needing human review |
| Eval suite | `python -m evals.run` | see numbers below |
| Claim-impact eval | `python -m evals.endtoend` | does an attack change the claim, not just get spotted |
| API server | `python -m uvicorn agents.server:app --port 8000` | 5 endpoints live |
| Public HTTPS | `cloudflared tunnel --url http://localhost:8000` | quick tunnel, no account |

`python -m evals.run` and `/assess` both work with **no API keys and no network**
(`FLOODVR_OFFLINE=1`): every model call falls back to a deterministic stub. The
demo cannot be taken down by the venue wi-fi.

## Attack numbers — report the last row

Four numbers, in the order they were measured. Only the last one is evidence.

| Set | Hijack, guard ON | What it is worth |
|---|---|---|
| Seed (39, we wrote them) | **0.0%** | Optimistic by construction — same author wrote attacks and rules |
| Held-out #1 (60, Claude), before tuning | **93.3%** | 4 of 60 caught. The rules only knew imperative verbs |
| Held-out #1, after tuning | **8.3%** | ⚠️ Now a **training** score. Rules were rewritten by reading its misses |
| **Held-out #2 (60, Claude), fresh** | **53.3%** | **The number we show judges** |

- False positives: **0 / 46** clean documents, including the real manifest note
  that says "total loss" and four that say "do not energize until inspected".
- Claim accuracy: **5 / 5** ground-truth checks. The kitchen ceiling stain is
  adjudicated wind-driven rain and excluded under `FL-EXCL-1`.

Tuning cut the real miss rate 93.3% → 53.3%, a 40-point gain that generalises.
The distance between 8.3% and 53.3% is overfitting, and it is only visible
because we generated a second set instead of quoting the first one back.

**What still gets through** is the subtle end, and may not be fixable with
rules: emotional pressure with no verb, the wind-vs-water argument made
plausibly, and "everything is minor, well under any threshold that would need
special review". A rule aggressive enough to catch those starts blocking honest
homeowners. **The argument is that detection is the weak layer and the
architecture is the strong one** — a live end-to-end run measuring exactly that
is in progress.

Each generated set costs ~11 cents of Anthropic credit. Use a NEW `--tag` after
tuning, or the number is measured on data the rules were fitted to.

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

## Agent status — honest version

README section 5 marks Orchestrator, Peril Adjudicator and Claim Writer as
built. That is too generous. Of the seven advertised LLM agents, **one actually
calls an LLM today.**

| # | Agent | Really an LLM? | State |
|---|---|---|---|
| 1 | Orchestrator | **No** | Sequences specialists, merges output, writes trace + audit log. Model id configured but **no tool-calling LLM call yet** |
| 2 | Intake (quarantined) | **Yes**, live | Nemotron 3.5 Lightning. No tools, returns only schema-validated fields, regex fallback |
| 3 | Peril Adjudicator | **No** | Deterministic, driven by `policy.json`, cites clause ids. 5/5 correct |
| 4 | Claim Writer | — | **Does not exist.** No narrative report for the adjuster |
| 5 | Vision Inspector | — | Not built. `vision_read()` is wired but has never seen a real screenshot |
| 6 | Consistency / Fraud Checker | — | Not built. The two severity-0 items are excluded but nothing cross-checks them |
| 7 | Voice Notes | — | Not built. Schema pushed for Mac 2 |
| tool | Hazard/Safety | No | Deterministic. 10 hazards, 6 at priority 1 |
| tool | Pricing | No, **by design** | `costs.json` only, clamped. Money must never come from an LLM |
| tool | Measurement | — | Not built. `house_geometry.json` is still unread |
| layer | Guard | Rules only | 27 rules. Guard-model layer off (see above) |

Deterministic peril and pricing is **partly a deliberate security property**: a
coverage decision that cannot be argued out of its answer is why a 53.3%
detection miss rate does not become a hijacked claim. But "the orchestrator
plans with Nemotron tool calling" is currently false, and the NVIDIA track
rewards Nemotron doing visible work.

Build order from here: Vision Inspector → real orchestrator tool calling →
Fraud Checker → Claim Writer → `/callouts` → console.

## Still blocked / needed

- Nothing blocking. Both API keys are in and working.
- `screens.json` and the severity-0 contents items have **landed** and are
  parsed; they are just not exercised yet by agents 5 and 6.

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
