# Mac 1 status

**Done:** House/damage pipeline, StandPoints, pre/post flood toggle, prompt-injection note, Capture Screens + screens.json, look polish, geometry export, contents fraud-checker items (prior rounds). This round: README section 2 StreamingAssets/config.json exception, section 4 heightAboveFloor semantics (0 = unset) -- also cleaned up 3 redundant explicit `heightAboveFloor: 0.0` entries in damage.json to match.

**Done:** ...plus FloodState.Toggle() + IsFlooded — runtime-safe public API (zero UnityEditor dependency, verified by code audit), documented in README 4.5 for Mac 2's gaze button. Everything it touches is already baked into House.unity, no extra wiring needed on their side.

**Done:** ...plus iPhone perf pass: static batching on everything whose transform never changes at runtime (excludes fridge + its note, and the 2 scaled cabinets), materials consolidated to shared-by-color except objects independently color-mutated by FloodState (those keep dedicated materials). Found and fixed a real bug along the way: all 6 outlets shared ONE material, so flagging one hazard-orange also flagged the 2 undamaged ones. Stats (analytical, via Tools > FloodVR > Report Scene Stats): 103 renderers, 1292 tris, 37 materials/batches -- both well under the 150-batch/100k-tri targets. Re-ran Capture Screens: screens.json byte-identical, only the 4 screenshots showing the now-fixed outlet color changed.

**Done:** ...plus smoke-tested Tools > FloodVR > Build Web (Mac 2's commits, not edited): clean batchmode build, 9.4 MB, House.unity confirmed still rig-free afterward (BuildWeb uses a throwaway scene copy). Served Builds/web locally and confirmed the CardboardVR template + loader/data/framework/wasm all serve correctly (desktop sanity check only, not deployed -- that's Mac 2's). Committed the ProjectSettings changes the build correctly applied (runInBackground, webGLTemplate, decompression fallback).

**Doing:** Idle, waiting on requests.

**Blocked:** Nothing.
