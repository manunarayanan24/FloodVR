# Mac 1 status

**Done:** House/damage pipeline, StandPoints, pre/post flood toggle, prompt-injection sticky note, Capture Screens, look polish (all prior round). This round: Tools > FloodVR > Export Geometry -> contracts/samples/house_geometry.json (per-room walls/openings/areas, waterline 0.9m, flood-cut 1.5m, metric+imperial) -- hand-verified living_room's wall-area math.

**Done:** ...plus Capture Screens now writes contracts/samples/screens/screens.json: filename/standpoint/position/yaw/pitch/fov + visible DamageItem/scene_text ids per frame (frustum + raycast, self-collider excluded). Caught and fixed a self-occlusion bug (objects were always "blocked by themselves") along the way.

**Done:** ...plus contents fraud-checker test cases: laptop (1.6m) + router (1.45m) on the bookshelf, tagged severity 0 "above waterline - no flood damage" via a new tagOnly effect type (ground-truth tag, zero visual change in either flood state); TV on its stand (base 0.6m, below waterline) tagged damaged. DamageItem gets a new heightAboveFloor field, threaded through the manifest. 26 items total, re-verified via rebuild + Capture Screens.

**Doing:** Wrapping up this round -- all 3 tasks complete.

**Blocked:** Nothing.
