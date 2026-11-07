# Mac 1 status

**Done:** House/damage pipeline, StandPoints, pre/post flood toggle, prompt-injection sticky note, Capture Screens, look polish (all prior round). This round: Tools > FloodVR > Export Geometry -> contracts/samples/house_geometry.json (per-room walls/openings/areas, waterline 0.9m, flood-cut 1.5m, metric+imperial) -- hand-verified living_room's wall-area math.

**Done:** ...plus Capture Screens now writes contracts/samples/screens/screens.json: filename/standpoint/position/yaw/pitch/fov + visible DamageItem/scene_text ids per frame (frustum + raycast, self-collider excluded). Caught and fixed a self-occlusion bug (objects were always "blocked by themselves") along the way.

**Doing:** Contents items (laptop/electronics above waterline, TV below) + heightAboveFloor field for the fraud checker.

**Blocked:** Nothing.
