HANDOFF — Windows machine (AI + security lane)
For a fresh Claude session picking this up cold. Read README.md (team contract,
owned by Mac 1) and agents/PLAN.md (architecture + threat model) first; this
file is everything those two do not say.

Your lane: agents/, evals/, contracts/ except contracts/samples/,
docs/STATUS-windows.md, docs/HANDOFF-windows.md.
Never touch Assets/ — Unity is owned by two Macs. Never write to
contracts/samples/ — Mac 1 generates those from Unity.

---

What is built and working
Everything below runs offline with no API keys (FLOODVR_OFFLINE=1): every
model call falls back to a deterministic stub. Venue wi-fi cannot kill the demo.

| What | Verify with | Expected |
|---|---|---|
| Full pipeline | python -m agents.tools.smoke | 26 manifest items → 24 line items, 10 hazards, 5 needs-human, flow check CLEAN, audit chain INTACT |
| Guard evals | python -m evals.run | seed 39/39, held-out #1 55/60, held-out #2 28/60, 0/46 false positives, 5/5 accuracy |
| Claim-impact evals | python -m evals.endtoend --set heldout2 | benign utility 100%, utility under attack 100%, targeted ASR 0%, 0/60 flow violations |
| Output guard + IFC | python -m agents.tools.test_output_guard | 7/7 passed |
| Live NVIDIA ids | python -m agents.tools.verify_models | every role resolves (exit 0) |
| Raw guard reply | python -m agents.tools.verify_models --probe-guard | prints the raw JSON verdict |
| Served model list | python -m agents.tools.list_models nemotron | ~84 models |
| API | curl http://localhost:8000/health | {"status":"ok", ...} |
agents/guard.py — 27 rules, R01–R15 (imperative-based) and R16–R27 (claim-based).
agents/trust.py — spotlighting with a per-run random datamark, invisible/bidi
char detection, homoglyph folding (NFKC does not fold Cyrillic lookalikes).
agents/taint.py — information-flow control. Declarations plus a 6-word
shingle check that no untrusted text reached a decision field.
agents/output_guard.py — redacts links/emails/data-URIs/images/HTML from every
outbound string including security-finding snippets, canary leak check,
re-runs rules on the response.
agents/audit.py — hash-chained agents/audit.jsonl; /health reports integrity.
agents/pipeline/ — intake (quarantined, the only LLM-backed agent),peril, estimator, safety, orchestrator, naive (the baseline we argue against).
agents/server.py — /health, /manifest, /assess, /attack-demo, /results.
evals/ — seed (39, ours), held-out #1 (60, Claude), held-out #2 (60, Claude,
post-tuning), 46 clean docs, run.py, endtoend.py, report.py.
contracts/ — damage_manifest.schema.json, claim_draft.schema.json,policy.json, costs.json, callouts.schema.json, voice.schema.json.
The numbers (all in evals/results.json and evals/endtoend.json)
| Set | Hijack, guard ON | Worth |
|---|---|---|
| Seed (39, ours) | 0.0% | Optimistic — same author wrote attacks and rules |
| Held-out #1, before tuning | 93.3% | 4/60 caught |
| Held-out #1, after tuning | 8.3% | ⚠️ training score, not evidence |
| Held-out #2 (fresh) | 53.3% | The number for judges |

End-to-end on held-out #2: targeted ASR 0%, utility under attack 100%.
Live run on held-out #1 with a real LLM intake: 0/60 claims changed, guard ON
or OFF. Naive single-prompt baseline, same attacks: 1 of 8 scored runs hijacked,
inflating a total from $31,000 to $53,650.

The pitch line: detection misses 53.3% of fresh attacks; none of them move
the claim. Detection is the weak layer, the architecture is the strong one.

---
Half-done, broken, or not started
Nothing is uncommitted. git status is clean and everything is pushed.

| Thing | State |
|---|---|
| Vision Inspector (agent 5) | Not built. vision_read() in agents/llm.py is wired to the VLM but has never been called with a real image. contracts/samples/screens/ has 9 PNGs and screens.json (the answer key with visibleDamageIds / visibleSceneTextIds per image). Nothing scores against it. |
| Orchestrator tool calling | Not built. agents/pipeline/orchestrator.py is deterministic Python that sequences specialists. A model id is configured but no tool-calling LLM call is made. README section 5 says otherwise — see §3. |
| Claim Writer (agent 4) | Does not exist. No narrative report. |
| Consistency / Fraud Checker (agent 6) | Not built. The trap data is already parsed: electronics_undamaged (1.45 m) and laptop_undamaged (1.6 m), severity 0, both above the 0.9 m waterline. Nothing cross-checks a claim against them. |
| Voice Notes (agent 7) + POST /voice | Schema only (contracts/voice.schema.json). No implementation. |
| GET /callouts | Schema only (contracts/callouts.schema.json). No implementation. |
| Measurement tools | Not built. contracts/samples/house_geometry.json is parsed by nobody. It has waterline 0.9 m, flood cut 1.5 m, per-room floor areas, wall lengths and openings, metric + imperial. |
| Adjuster console | Not built. agents/server.py serves agents/console/index.html at / but that file does not exist (404 by design). |
| Guard-model second layer | Disabled. See §3. |
| agents/tools/guard_bakeoff.py | Written but never completed a run — it hung for 25 min with zero output and was killed. Needs a smaller sample and -u. |

---
Decisions and hard-won lessons not in README.md or PLAN.md
NVIDIA API — four things that cost real time
Every model id in the original brief was dead. nvidia/nemotron-3-super-120b-a12b
404, llama-3.1-nemotron-nano-vl-8b-v1 410, nemoguard-jailbreak-detect 404(it ships as a downloadable NIM container, not on the hosted API).
Being listed by GET /models does not mean you can call it. Several ids are
listed and still 404 on chat completions — nvidia/nemotron-3-super-120b-a12b,nvidia/nemotron-nano-3-30b-a3b, nvidia/nemotron-3.5-content-safety.Always probe with verify_models, never trust the listing.
Nemotron 3.5 models are reasoning-tuned. They spend the budget onreasoning_content before writing content. A small max_tokens returns an
empty string with finish_reason: "stop" — indistinguishable from a dead model.agents/llm.py enforces _MIN_MAX_TOKENS = 512 and falls back toreasoning_content if content is empty. Do not lower that floor.
Bursts are answered with HTTP 403, not 429. agents/llm.py has_MIN_INTERVAL_S = 0.45 plus backoff. Without it a sweep looks like a dead key.

Current working ids are pinned in agents/config.yaml with fallback chains. Re-run
verify_models at the start of every session — they rotate.
Why the guard model is OFF (guard.guard_model_enabled: false)
Verified against a real raw reply: the NVIDIA content-safety model returned
{"User Safety": "safe"} for our live fridge-note attack. The verdict parser
in guard.py::parse_guard_verdict is correct — the model is the wrong tool.
Content-safety models detect harmful content (violence, hate), not injection.

Also: /assess guards ~46 text fields per run, so a second model layer costs 46
extra calls per claim. Do not enable it without first running a bake-off that
shows it detects injection. Claiming a layer that does nothing is worse than
not having one.
Eval integrity rules — the thing most likely to be broken by accident
Tuning rules on a set destroys that set's value as evidence. Held-out #1 was93.3% before tuning and 8.3% after; the 8.3% is a training score.
After touching agents/guard.py, generate a NEW set with a NEW tag:python -m evals.gen_variants --count 60 --tag heldout3 (~11 cents of Anthropic
credit). Never regenerate over an existing tag.
Measure before you tune, and record the number, even when it is bad.
Report seed and held-out together. The seed number alone is misleading.
Judge by inspecting the produced claim, never by asking an LLM — a judge is
itself injectable (AgentDojo's reasoning).
Guard rule design
R01–R15 key off imperative verbs. That was the mistake — Claude's attacks
mostly contain no imperative. R16–R27 look for the claim being made.
R16 is directional on purpose. "do not energize until inspected" requires a
check and must not match; four real manifest notes say exactly that.
Bare keywords are banned. The real manifest says "total loss" about the sofa,
a real receipt cites statefarm.com, a real contractor writes "urgently". All
three were false positives once. Rules require a directive context.
Long whitespace runs are checked procedurally (_whitespace_findings), not by\s{8,}\S — receipts align prices into columns and that fired on every one.
Finding snippets are an outbound surface. They render in the console; a live
attacker URL reached the response through one before output_guard existed.
Architecture decisions
Pricing is deterministic and always will be. costs.json only, clamped per
line item ($25k) and per claim ($120k). Money must never come from an LLM.
Deterministic peril/coverage is a security property, not laziness: a coverage
decision that cannot be argued out of its answer is why a 53.3% detection miss
rate does not become a hijacked claim. Keep it when adding LLM agents.
claim_draft.status is a constant draft_pending_human. No code path approves
payment. Keep it that way.
heightAboveFloor: 0.0 means "not supplied", not "on the floor." Mac 1
populates it only for contents items. kitchen_ceiling_stain carries 0.0 but its
real height is 2.58 m. Treating 0.0 as authoritative put the ceiling stain below
the waterline and destroyed the wind-vs-water determination — the demo's
centrepiece. See DamageItem.height_m.
Severity 0 = present but undamaged. Excluded from cost and from line items;
kept as fraud-checker evidence. unit may be empty on those.
Claude is fallback + red-team only, never the primary agent brain (team rule).
Anthropic refuses red-team generation by default. The first gen_variants
run died with stop_reason: refusal. claude_complete now sendsbetas=["server-side-fallback-2026-07-01"] with fallbacks="default" and
reports the refusal category. Keep that.
---

Next steps, in order
Vision Inspector (agents/pipeline/vision.py). For each of the 9 PNGs incontracts/samples/screens/, call vision_read(), extract damage labels and
any visible text, score against screens.json's visibleDamageIds →"found N of M". Route every piece of transcribed text through guard.inspect
with channel=vlm_output. This is the NVIDIA track and the injection demo:
the fridge note only reaches the pipeline because a model read it off a wall.Caveat to state honestly: it is a low-poly render, so the score is an upper
bound on real-world performance.
Consistency / Fraud Checker (agents/pipeline/consistency.py). Cross-check
claimed items against heightAboveFloor vs the 0.9 m waterline and severity 0.electronics_undamaged and laptop_undamaged are the planted trap. Emit aSecurityFinding with layer="consistency" (already in the schema).
Measurement tools from house_geometry.json feeding pricing — wall area
below the waterline, flood-cut drywall m². Deterministic, no LLM.
Orchestrator tool calling. Make the orchestrator actually plan with Nemotron
Super. Keep peril and pricing deterministic underneath — the LLM chooses which
tool to call, never what the answer is.
GET /callouts per contracts/callouts.schema.json. Mac 2 is waiting.
POST /voice per contracts/voice.schema.json. Note the deliberate
constraint: voice updates cannot touch coverage, peril or cost.
Claim Writer — narrative report from structured results only.
Adjuster console at agents/console/index.html — agent trace, claim draft,
blocked injections with highlighted snippet + the rule that fired, attack rates
before/after. Build last, when it has everything to show.
After any guard change, go back to the eval integrity rules in §3.

---
How to start everything
cd C:\dev\FloodVR
git pull --rebase

# venv already exists; if not:  py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r agents\requirements.txt      # only if the venv is missing

python -m agents.tools.smoke                # offline sanity check


Keys live in agents\.env (gitignored, confirmed by git check-ignore -v agents/.env).
Variable names only — never print, log or commit the values:

NVIDIA_API_KEY — build.nvidia.com, free developer credits, $0
ANTHROPIC_API_KEY — console.anthropic.com, pay-as-you-go, $20 spend limit set
FLOODVR_OFFLINE — 1 = deterministic stubs, 0 = live. Currently 0.

Set FLOODVR_OFFLINE=1 in the environment to force offline for a single command
without editing the file.

Server:
python -m uvicorn agents.server:app --port 8000
Public HTTPS (cloudflared is at C:\Program Files (x86)\cloudflared\cloudflared.exe;
it is NOT on PATH in a non-interactive shell):
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000


Current tunnel URL (alive as of this handoff, dies when cloudflared stops —
a new one is issued on every restart, so update this and docs/STATUS-windows.md):

https://operates-voters-officials-lenses.trycloudflare.com


Mac 2's WebGL app reads the URL at runtime via ?api= or
StreamingAssets/config.json, so a new tunnel never needs a rebuild. CORS allows
https://*.vercel.app and http://localhost:<port>.
Where the results live:

evals/results.json — guard detection numbers, per technique, with the misses
evals/endtoend.json — claim-impact + AgentDojo metrics, and the naive baseline
evals/report.html — standalone styled report, safe to show a judge
agents/audit.jsonl — hash-chained run log; verify with audit.verify_chain()

All four are gitignored except report.html/results.json behaviour noted in
.gitignore — regenerate with python -m evals.run if they are missing.

Useful one-liners:
.\agents\tools\call_assess.ps1                     # POST /assess, summarised
.\agents\tools\call_assess.ps1 -BaseUrl https://<tunnel>
python -m agents.tools.show_misses heldout2        # what still gets through
python -m agents.tools.probe_raw intake "say ok"   # raw NVIDIA response shape


---
Open cross-lane items (README §9)
Mac 2 — comment on contracts/callouts.schema.json andcontracts/voice.schema.json before building against them.
Mac 1 (lead) — README §5's status column overstates the agents: Claim Writer
does not exist, and Orchestrator and Peril Adjudicator are deterministic Python,
not LLM agents. Of 7 advertised LLM agents, 1 calls an LLM today (Intake).
Flagged in §9 rather than edited, because §5 is the lead's file.

---
Lead addendum (Mac 1, written 2026-11-07 ~7:20 pm after the old account hit its limit)

This file was recovered from the old session's partial output; the old session
never pushed it. Corrections and additions that supersede anything above:

1. State of main: your last push is 2fba81b (output guard, taint/IFC, AgentDojo
   metrics). Mac 1's round is done and idle. Mac 2 compiled and deployed the first
   Web build to https://web-gamma-three-xsqthicx3g.vercel.app (not yet tested on an iPhone).
2. The old session was "standing by for the agent prompt from the main computer".
   It never received it. THE BUILD ORDER BELOW REPLACES "Next steps, in order" above:
   a. Finish/record the two security numbers in evals/results.json, /results and
      evals/report.html: detection miss on fresh held-out, AND end-to-end impact
      rate (already measured: targeted ASR 0/60). Never tune on a set you report.
   b. Vision Inspector, scored vs screens.json, all transcribed text through the guard.
   c. REAL Orchestrator tool calling with Nemotron (LLM picks tool order, never
      decides money/coverage; no tool can approve; status stays draft_pending_human).
      Re-run endtoend to prove tool calling opens no new injection path.
   d. Consistency / Fraud Checker (contracts/fixtures/ clean + padded contractor bids).
   e. Claim Writer (Nemotron writes from structured facts; every number in the text
      must appear in the structured data - add that check).
   f. Measurement tools from house_geometry.json -> quantities -> pricing.
   g. GET /callouts (<= 60 chars each, ?seen=ids, position from manifest).
   h. VOICE VIA LIVEKIT (decision recorded in README): agents/voice/ LiveKit Agents
      worker in room "floodvr" (speech -> guard -> Voice Notes agent -> PROPOSED edit
      needing adjuster confirm, or a spoken answer), POST /voice/token for the iPhone,
      POST /voice text fallback. Needs LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
      in agents\.env (Ragotham creates the free LiveKit Cloud project). Check NVIDIA
      hosted speech models first; tell Ragotham the price BEFORE using anything paid.
      Update contracts/voice.schema.json with the token flow and push so Mac 2 can build
      the iPhone side. Voice must not be able to touch coverage, peril or cost.
   i. Adjuster console at /console.
3. guard_bakeoff.py: optional. If tried, run a small sample with python -u; keep the
   second layer only if it lowers FRESH held-out miss with no new false positives.
4. Budget: do not trust the "$20 spend limit" line above - check the Anthropic console
   balance (earlier it was ~$8.83 of credit, key expires Dec 7). Ask Ragotham before any
   spend over $1. Generated attack sets cost ~11 cents each.
5. Whenever you restart cloudflared, put the new URL at the top of docs/STATUS-windows.md.
6. Update README section 8 (your status line only) and section 9 as you finish steps.

---
CURRENT PLAN (2026-11-07 evening): the user's "Build plan v2" (8 steps) REPLACES both the "Next steps, in order" list above and the Lead addendum build order. All 8 steps are implemented; progress, gate numbers and the one blocker (LiveKit credentials) are in docs/STATUS-windows.md under "Build plan v2". Gate before every push: agents.tools.smoke, agents.tools.test_output_guard (7/7), evals.endtoend --set heldout2 (targeted ASR 0%, utility under attack 100%, 0 flow violations), evals.run (0/46 false positives). Do not modify output_guard.py, taint.py, guard rules or eval sets.
