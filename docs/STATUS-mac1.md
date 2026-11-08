# Mac 1 status

**Done:** House/damage pipeline, StandPoints, pre/post flood toggle, prompt-injection note, Capture Screens + screens.json, look polish, geometry export, contents fraud-checker items (prior rounds). This round: README section 2 StreamingAssets/config.json exception, section 4 heightAboveFloor semantics (0 = unset) -- also cleaned up 3 redundant explicit `heightAboveFloor: 0.0` entries in damage.json to match.

**Done:** ...plus FloodState.Toggle() + IsFlooded — runtime-safe public API (zero UnityEditor dependency, verified by code audit), documented in README 4.5 for Mac 2's gaze button. Everything it touches is already baked into House.unity, no extra wiring needed on their side.

**Doing:** iPhone perf pass (static batching, stats capture).

**Blocked:** Nothing.
