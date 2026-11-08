# Machine 3 (Windows) — AI + security status

**Tunnel (live): https://achieve-custom-pressed-ellen.trycloudflare.com** (restarted 2026-11-08 08:36 after the PC slept;
the old `starter-king-jackson-avon` URL is dead). `/health` ok, live NVIDIA, audit chain intact.
Console: `<tunnel>/console` · Voice test: `<tunnel>/voice-test`.

**Mac 2:** the deployed app still has the old URL in `Assets/StreamingAssets/config.json`. Until it is rebuilt, open
`https://web-gamma-three-xsqthicx3g.vercel.app/?api=https://achieve-custom-pressed-ellen.trycloudflare.com`
(ApiConfig's `?api=` override, remembered in localStorage).

Owner: Abhinav. Lane: `agents/`, `evals/`, `contracts/` except `contracts/samples/`, `docs/STATUS-windows.md`,
`docs/HANDOFF-windows.md`. Nothing under `Assets/` is modified. Last updated: 2026-11-08 ~10:00.

## Done / Doing / Blocked

- **Done (lead requests, README §9, Sun 8 Nov):**
  - **`/assess` 524 fixed** (`74166f7`). Hard time budget: planner 25 s, whole request 55 s; every LLM call gets
    only the time left (SDK retries off); when spent, the remaining stages run in fixed order (claim identical).
    On a 429 the planner switches to the next served model at once. Through the tunnel: **HTTP 200 in 30.4 s and
    28.7 s** (was >100 s / 524), same totals and status. Cause of this morning's 429s: two of my background planner
    evals were still hitting the orchestrator model; stopped.
  - **Voice answers** (`396007b`): template answers from claim data + geometry for water height, flood cut,
    drywall amount and cost (house or per room), mold, per-room damage/cost/size, laptop/router, the fridge note
    and "what did I miss?" (gaze history: the LiveKit worker sends `seen_item_ids`; `/callouts?seen=` also feeds
    it). Items named out loud beat the classifier's guess. `python -m evals.voice`: **27/27 live, 27/27 offline**
    on a 27-question DEV set over the weak topics (built from it, so not a held-out number). Guard unchanged:
    instructions refused, voice can't touch cost.
  - This file and the README §8 Windows line refreshed.
- **Voice is OPEN MIC (2026-11-08):** `/voice/client.js` turns the mic on at connect and keeps it on (echo cancellation, noise suppression); the agent answers 2 s after the adjuster stops talking (VAD + final transcripts), never interrupts itself, and ignores speech heard while it talks or that repeats its last reply. `setMic()` is a no-op so the app's old tap toggle is harmless; `setMuted()` added; `/voice-test` has a Mute button and shows a real error if the mic is blocked. Tested: two-part question with a pause → one answer; the agent's own reply played back into the room → ignored. **Mac 2 must add one `Connect()` call** (the app never starts LiveKit today) — `contracts/voice_unity/README.md`.
- **Voice routing reworked (lead, Sun 8 Nov):** one ordered router (`agents/voice/notes.py: route`): change requests → fixed refusal; approval/payment → draft answer only when asked; help; injection; summary; room ranking; missed; then an ITEM (named out loud > "this/that" + gaze > gaze when nothing else is the subject; a named or gazed item beats a room word; id words outweigh description words; topic words like mold/waterline and ties never name an item; everyday synonyms) with one rich answer (label, severity in words, measurement, estimate, coverage + clause, hazard + action, asked-about part first); then room; then house-wide topics; **unknown → help line, never the total**. **Held-out (`evals/voice_heldout.json`, 30 new phrasings written after the rework, scored once before any change): 25/30 (83%), live classifier** — misses: "How deep was the flooding in here?"; "Did the computer on the shelf get wet?"; "Is somebody gaming the system here?"; "Where's the worst damage in the house?"; "Is the water heater a danger?". Raw first run kept in `evals/voice_heldout_first_run.json`. Fixed afterwards (word forms, synonyms, trickery phrasings, "where's the worst damage", id-word weighting): 30/30, which is now a TRAINING score. Dev set (`evals/voice_questions.json`, incl. the lead's 9 misses): 40/40 live and offline. Refusals still refuse ("approve the max payout", "set the estimate to fifty thousand", "bump the payout to the maximum").
- **Printable claim report (lead, Sun 8 Nov):** `GET /report` (page) + `GET /report/data` (JSON). Latest guarded `/assess`, else the fixed-order baseline with a Claim Writer report. DRAFT stamp, date, totals (flood vs homeowners), adjuster report, line items (room, peril, policy + clause ids, quantity, estimate), hazards by priority with actions, review list and flagged findings, blocked injections as rule names + counts only (never the text), flow-control result. Every string through output_guard; rendered with textContent. Print CSS: ~1.9 US-letter pages; "Save as PDF" calls window.print(). Console Claim tab: "Open report" after a run.
- **Doing:** nothing. Waiting for Mac 1's re-export to re-run the Vision Inspector cache (`evals/vision.json`).
- **Blocked:** none. Keep this PC awake (sleep set to Never) — the quick tunnel URL changes if it sleeps.
- **Not re-run:** the Nemotron-planner end-to-end eval (`--planner`) on the new budgeted planner. Its last numbers
  (0/60 changed, 0 flow, 0 transcript leaks; 49/120 runs needed enforced stages because of 429s) predate the
  budget. The fixed-order gate passes on the pushed tree. Re-running costs ~120 planner runs against the same
  model the live demo uses, so I'd run it off-hours.

## Gate on the pushed tree

smoke CLEAN / audit chain INTACT · test_output_guard 7/7 · evals.run 0/46 false positives, 5/5 claim accuracy ·
**endtoend heldout2 (fixed): 0/60 claims changed guard ON and OFF, targeted ASR 0%, utility under attack 100%,
0 flow violations** · offline (`FLOODVR_OFFLINE=1`) smoke passes. Protected files untouched.

## Agents (verified live Sun 8 Nov)

| # | Agent | Runs on | Job |
|---|---|---|---|
| 1 | Orchestrator | Nemotron 3.5 Super, native tool calls | Picks stage order from 9 tools; sees counts only (shingle-checked per run); 25 s budget, then fixed order |
| 2 | Intake (quarantined) | Nemotron 3.5 Lightning | Only reader of raw evidence; no tools; schema-validated fields only |
| 3 | Peril Adjudicator | deterministic (`policy.json`) | Flood vs wind-driven rain with clause ids |
| 4 | Claim Writer | Nemotron (thinking off) | Adjuster report; every number checked against the draft; template fallback; within the request budget |
| 5 | Vision Inspector | Nemotron 3.5 Super VL | 9 screenshots vs `screens.json` (5 hits / 5 false, recall 31% on low-poly renders); transcribed text → guard |
| 6 | Consistency / Fraud Checker | deterministic | Undamaged items claimed, above-waterline, padded bids, bid quantities vs geometry, items not in scene (11/11) |
| 7 | Voice Notes | LiveKit + NVIDIA Parakeet / Magpie + Nemotron Lightning (intent) | Template answers from claim data; notes become proposals; one answer per question (push-to-talk signal) |
| tools | Hazard · Pricing · Measurement | deterministic | Hazard ranking; `costs.json` × measured quantity, clamped; areas from `house_geometry.json` (matches Unity) |
| layers | Guard · Output guard · Flow control · Audit | deterministic | 27 rules; outbound scrub; taint + shingle proof; hash-chained `audit.jsonl` |

## Live API

Base URL: the tunnel above. Quick tunnels die when `cloudflared` stops or the PC sleeps — read the URL at runtime
(`?api=`), never bake it into a build. CORS allows `https://*.vercel.app` and `http://localhost:<port>`.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | offline flag, key presence, model ids, audit-chain status |
| `GET` | `/manifest` | Mac 1's `contracts/samples/house_manifest.json` |
| `POST` | `/assess` | claim draft (`?planner=llm` default, `fixed`; `?report=true`); ≤55 s |
| `POST` | `/attack-demo` | one attack, guarded vs unguarded |
| `GET` | `/results` | eval numbers + headline |
| `GET` | `/callouts` | headset callouts (`?seen=`; `kind=missed`) |
| `GET` | `/vision` · `/measurements` | Vision Inspector (cached) · room quantities + Unity cross-check |
| `POST` | `/voice` · `/voice/confirm` · `GET /voice/pending` | text voice path (`seen_item_ids` optional) · proposals |
| `POST` | `/voice/token` · `/voice/agent` | LiveKit join token (agent `floodvr-voice` dispatched) · re-request the agent |
| `GET` | `/voice/client.js` · `/voice-test` · `/console` | headset voice client · phone test page · adjuster console |

Processes on this PC: `uvicorn agents.server:app --port 8000`, `cloudflared tunnel --url http://localhost:8000`,
`python -m agents.voice.worker dev`.

## Security numbers (report together)

Held-out #2 (60 Claude-written attacks, never used for tuning): detection misses **53.3%** (32/60), yet **0/60
attacks changed the claim** (guard ON and OFF). Utility under attack 100%; 0/46 false positives; 5/5 accuracy.
Detection is the weak layer; the architecture is the strong one. (Seed set 0% and held-out #1 after tuning 8.3% are
training scores; held-out #1 before tuning was 93.3%.)

## Where the numbers come from (0.9 m, 1.5 m, 86.1 m²)

- **0.9 m waterline** is authored by Mac 1: the `waterline` item's `effect.heightM` in the damage data. Unity draws
  the wall stain band at that height (`Assets/Editor/DamageBuilder.cs`) and `GeometryExporter.cs` writes the same
  value to `contracts/samples/house_geometry.json`. One source for the visuals and the numbers.
- **1.5 m flood cut** = waterline + a fixed 0.6 m margin in `GeometryExporter.cs` (cutting drywall a couple of
  feet above the waterline is standard restoration practice; the margin is a design choice).
- **86.1 m² of drywall** is computed from the model's real walls: the exporter writes every wall's length/height
  and every door, window and archway; `agents/pipeline/measure.py` does wall length × 1.5 m − openings per room
  (living room: 22 m × 1.5 m − 7.95 m² = 25.05 m²) and cross-checks Unity's own totals (all 4 rooms match).
  Pricing: 86.1 m² × $35–85/m² (`contracts/costs.json`) = the $3,014–$7,319 drywall line.
- The agents never measure the 3D scene visually; they read the exported geometry + damage manifest. The Vision
  Inspector looks at screenshots only to demo detection and feeds no decision.
- So the house, flood level and damage are a designed scenario; everything computed from them is real arithmetic
  on the model's geometry. If Mac 1 changes the waterline or a wall and re-exports, flood cut, drywall area and
  price follow automatically with no Windows change.

## Design decisions worth knowing

- Only Intake reads raw untrusted text; the planner sees counts; voice replies and callouts are server templates.
- Money comes only from `contracts/costs.json` × measured quantity, clamped. `status` is always
  `draft_pending_human`; no code path approves payment.
- Every LLM call has an offline stub; `FLOODVR_OFFLINE=1` runs everything with no network.
- NVIDIA's content-safety model scores our injections "safe", so the guard-model layer stays off.
- `contracts/samples/` is Mac 1's lane and is never written from Windows.

Earlier history (build order a→i, build plan v2, LiveKit bring-up) is in git log.
