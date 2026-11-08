# Machine 3 (Windows) — AI + security status

**Tunnel (live): https://starter-king-jackson-avon.trycloudflare.com** — `/health` ok, live NVIDIA, audit chain intact. Console: `<tunnel>/console`.

## Build order (lead addendum a→i) — progress

- [x] **a. Two security numbers recorded** — `evals/headline.py` merges detection (results.json) + end-to-end impact (endtoend.json) into `results.json["headline"]`, served by `GET /results`, top of `evals/report.html`. Held-out #2: **detection miss 32/60 (53.3%)**, **claim changed 0/60 (0.0%)** guard ON and OFF, live LLM intake.
- [x] **b. Vision Inspector** — `agents/pipeline/vision.py`, `GET /vision` (cached in `evals/vision.json`; ~9 VLM calls/run). Nemotron VL picks visible damage from a closed list + transcribes text; every transcription → guard (`vlm_output`). **Live: 5 correct / 5 extra detections (precision 50%, recall 31%), 3/7 unique items.** Fridge note transcribed in 2/3 kitchen shots, **blocked in 1/3** — the note's text overflows its yellow backing and wraps one word per line, so the VLM reads fragments (request to Mac 1 below). Low-poly renders: not a real-world detection score. VLM picks never set peril/coverage/cost.
- [x] **c. Orchestrator tool calling** — `agents/pipeline/planner.py`: Nemotron Super picks stage order with native tool calls (`run_guard`, `run_intake`, `adjudicate_coverage`, `triage_hazards`, `inspect_screens`, `check_consistency`, `finalize_draft`). `orchestrator.Run` enforces order (intake refuses before guard; finalize runs skipped stages); no approve tool; status constant. The planner sees **counts only**, proven per run by shingle-checking its whole transcript (`flow_control.planner_transcript_clean`). `POST /assess` uses it by default (`?planner=fixed` for the old path). Live: 7 tool calls in 4 turns, ~12 s, claim identical to fixed order. Refactor verified output-identical. **End-to-end on held-out #2 with the planner (live): 0/60 claims changed guard ON and OFF, 0 flow violations, 0 planner-transcript leaks, 0 runs needing enforced stages** (`evals/endtoend_planner.json`, in the `/results` headline).
- [x] **d. Consistency / Fraud Checker** — `agents/pipeline/consistency.py`, a `Run` stage + planner tool `check_consistency`. Deterministic, reads only schema-validated evidence + manifest; raises `layer=consistency` findings (`claimed_undamaged`, `above_waterline`, `padded_bid` >1.25x our rate-table high, `total_loss_claim`), **never edits the claim**. Fixtures `contracts/fixtures/consistency_cases.json` (clean + padded bids, the laptop/electronics trap). `python -m evals.consistency`: **7/7, precision 1.0, recall 1.0, 0 claims changed — offline and with live LLM intake.**
- [x] **e. Claim Writer** — `agents/pipeline/writer.py`. Nemotron (thinking off, ~3-4 s) writes a 4-paragraph adjuster report from a facts dict built from the finished draft — no evidence or scene text. **Every number in the prose, digits or spelled-out, must appear in the facts** (`number_check`); one retry naming the bad numbers, then a deterministic template. Output guard + shingle leakage check applied. Returned as `adjuster_report` on `POST /assess` (`?report=false` to skip); added to `contracts/claim_draft.schema.json` (with `flow_control`). Live: 18 numbers checked (incl. spelled-out), 0 unsupported. Found on the way: reasoning-mode Nemotron returned its chain of thought as content; `nvidia_chat` now accepts `extra_body` to disable thinking.
- [x] **f. Measurement tools** — `agents/pipeline/measure.py` recomputes per-room floor area, wall area below the 0.9 m waterline, flood-cut drywall area (to 1.5 m) and baseboard run from raw walls/openings; **cross-check vs Mac 1's exported totals: all 4 rooms match.** House: 80.0 m² floor, 53.28 m² below waterline, 86.1 m² flood cut, 59.2 m baseboard. `costs.json` types gain `per_geometry` rates; estimate = max(table base × severity, rate × quantity), still clamped; each line item carries `quantity` (contract updated) and the ledger records the geometry source. Only `waterline_band` moved ($3,014–$7,319 for 86.1 m² flood cut): claim total now **$23,069–$70,478** (was $22,855–$69,659). `GET /measurements`.
- [x] **g. `GET /callouts` — live.** `agents/pipeline/callouts.py`. 16 callouts on the baseline: 6 priority-1 hazards, the fridge-note `blocked` (amber, anchored by scene-text id), structural/mold hazards, the wind-driven-rain coverage call, waterline 0.90 m + 86.1 m² flood cut, and the two green undamaged contents items. Text ≤60 chars, all server templates (never evidence/scene text). `?seen=` filter; positions from manifest (+0.35 m). Reflects the latest guarded `/assess` (e.g. a claim on `laptop_undamaged` adds an amber "Claim conflicts with the scene" callout), else a cached baseline; byte-stable between runs so Mac 2's 45 s poll doesn't re-render. Schema-checked against `contracts/callouts.schema.json`.
- [~] **h. Voice — built; LiveKit leg waits on credentials.** `agents/voice/notes.py` (Voice Notes agent): transcript → guard (`voice_transcript`, untrusted) → Nemotron Lightning (thinking off, spotlit, JSON only) classifies intent/topic and extracts **proposals** limited to `adjuster_note|disputed|needs_photo|severity_opinion|access_blocked`; the **spoken reply is a template over claim data**, never LLM prose. Live tests: coverage/cost/hazard questions answered from the draft, "needs a photo" and "I dispute the crack" become proposals, "approve maximum payout" and "set the estimate to fifty thousand" are **refused** at the guard. `POST /voice` (text fallback), `POST /voice/confirm`, `GET /voice/pending`, `POST /voice/token` (stdlib HS256 LiveKit JWT; **503 until LIVEKIT_* set**, verified with test creds). `agents/voice/worker.py`: LiveKit worker, NVIDIA Riva Parakeet STT + Magpie TTS (**$0, NVIDIA credits**), no LiveKit LLM, reply JSON on data topic `floodvr.voice`, gaze on `floodvr.gaze`. Import-checked; **not run against a live room yet**. `contracts/voice.schema.json` updated with the token flow for Mac 2.
- [x] **i. Adjuster console** at `/console` (and `/`): `agents/console/index.html`, no build step, all API data rendered via `textContent`. Tabs: Security (both headline numbers, per-set table, planner impact), Claim (presets: injection / laptop fraud / padded / honest bid; Nemotron-planned run with agent trace + tool calls, totals, number-checked report, findings with snippet + rule, hazards, review list, line items with geometry quantities, flow-control result), Attack demo (guarded vs unguarded), Vision (9 screenshots via `GET /screens/{name}`, allow-listed from screens.json), Voice (send + confirm/reject proposals), Headset (live callouts + measurements). Verified in a browser against the live server: no console errors.

## Build plan v2 (user, 2026-11-07 evening) — progress

Replaces the Next-steps list and Lead addendum in `docs/HANDOFF-windows.md`. Gate run on the pushed tree:
smoke CLEAN/INTACT · test_output_guard 7/7 · evals.run 0/46 false positives, 5/5 accuracy ·
**endtoend heldout2 (fixed): claims changed 0/60 guard ON, 0/60 guard OFF; targeted ASR 0%; utility under attack 100%; flow violations 0** · **endtoend heldout2 (Nemotron planner): claims changed 0/60 guard ON, 0/60 guard OFF; targeted ASR 0%; utility under attack 100%; flow violations 0;
planner transcript leaks 0, runs with enforced stages 49** ·
evals.consistency 11/11 (live intake) · offline (FLOODVR_OFFLINE=1) smoke/voice/callouts pass.
Protected files untouched: `agents/output_guard.py`, `agents/taint.py`, guard rules, eval sets.

1. **/callouts** — done earlier; now `kind=missed` for damaged items not in `?seen=` (labels via output_guard). Schema text updated.
2. **Vision** — new `vision` stage in every `/assess` trace ("found 5 of 16 … upper bound: low-poly render"); VLM transcriptions registered as untrusted in the flow ledger and guarded (fridge note flagged by 3 rules in the legible frame, 1/3 frames); feeds no decision; `/vision` output scrubbed by output_guard.
3. **Measurements** — new `measure` stage; the trace shows the arithmetic per room (e.g. `22 m wall x 1.5 m - 7.95 m2 openings = 25.05 m2`) and per priced line (`86.1 m2 x $35-85/m2 … estimate = max`), plus the Unity cross-check.
4. **Consistency** — added `bid_quantity_exceeds_measured` (stated drywall/flooring/baseboard vs geometry, 10% tolerance) and `item_not_in_scene`; intake extracts `claimed_quantities` + `unlisted_items` (bounded, charset-restricted); every snippet carries `[refs: …]`. Findings only — needs_human/money unchanged (keeps the endtoend fingerprint honest). 4 new fixtures.
5. **Orchestrator** — tools split: `run_guard, run_intake, inspect_screens, measure_house, adjudicate_peril, price_items, check_consistency, triage_hazards, finalize_draft`; Run enforces order (price needs peril+measure); every tool call is an `audit.jsonl` record (`tool_call`) and in the trace. Decisions verified identical to HEAD on 4 scenarios before the eval.
6. **Claim Writer** — paragraphs now: hazards → totals + line items with clause ids (ADJ-1, FL-COV-1, FL-EXCL-1…) → flagged findings + review list → blocked injections (counts, never quoted). Live: 29 numbers checked, 0 unsupported.
7. **Voice** — `python -m agents.tools.probe_speech`: **NVIDIA hosted Magpie TTS (1.0 s) and Parakeet ASR (0.8 s) work with our key, $0.** Nothing paid needed. **LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are missing from agents\.env** — `/voice/token` returns 503 until they are added; text `/voice` works.
8. **Console** — strings from `/attack-demo` (input + snippets) and `/results` (missed-attack texts) now pass output_guard server-side; impact card labelled Targeted ASR.

## Next / blocked

- **Reliability finding (planner eval):** NVIDIA returned **HTTP 429 on the orchestrator model in 50/120 runs**, and both configured fallbacks (`llama-3.1-nemotron-ultra-253b-v1`, `llama-3.1-nemotron-70b-instruct`) now **404**. Those runs fell back to the fixed order (claim identical, gate unaffected) — so Nemotron actually planned 70/120 runs. Fix next: retry/backoff on 429 in `planner.py` (as `nvidia_chat` already does) and re-probe fallback ids with `verify_models`.

- **Blocked:** LiveKit Cloud credentials (free plan) still missing from `agents\.env` → then run `python -m agents.voice.worker dev` and test a live room. Everything else in voice works now as text.
- **Asked Mac 1:** make the fridge note legible to the VLM (text overflows the yellow note; blocked in 1/3 shots).
- **Asked Mac 2:** `/callouts` and `/voice` are live; LiveKit flow is in `contracts/voice.schema.json`.
- Optional: guard-model bake-off (addendum item 3) — not attempted. Anthropic spend this session: **$0**.

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
| `GET` | `/callouts` | live | headset callouts, `contracts/callouts.schema.json` (`?seen=`) |
| `GET` | `/vision` | live | Vision Inspector result (cached) |
| `GET` | `/measurements` | live | room quantities + cross-check vs Mac 1 export |
| `POST` | `/voice` | live | text voice path, `contracts/voice.schema.json` |
| `POST` | `/voice/confirm` | live | adjuster accepts/rejects a proposal |
| `GET` | `/voice/pending` | live | proposals awaiting confirm |
| `POST` | `/voice/token` | 503 until LiveKit creds | LiveKit join token, room `floodvr` |

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
