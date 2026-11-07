# Mac 1 status

**Done:** House + damage pipeline. StandPoint_Hallway/Living/Kitchen added. TextMeshPro imported. Pre/post flood toggle: FloodState.Show(bool) + FloodVisual components + Tools > FloodVR > Show Pre-Flood/Post-Flood menu items; waterline refactored to a pure additive overlay so it can be hidden cleanly.

**Done:** ...plus a prompt-injection sticky note on the fridge (TextMeshPro 3D text + SceneText component), exported in damage_manifest.json under a separate "scene_text" array, not as a DamageItem.

**Done:** ...plus Tools > FloodVR > Capture Screens: 9 1280x720 PNGs (3 StandPoints x 3 angles) into contracts/samples/screens/, manifest copied to contracts/samples/house_manifest.json. Verified by viewing renders -- fixed a mirrored-text bug in the sticky note along the way (TMP backface was pointing into the room).

**Done:** ...plus look polish: outdoor flood water frame around the house at 0.3m (visible through windows, excludes the interior footprint), grey overcast sky + fog via solid-color camera clear (no skybox), dimmer light (0.8), flat ambient, 3 floor puddles. No realtime shadows; verified by re-running Capture Screens and eyeballing renders.

**Doing:** Writing this status doc / wrapping up.

**Blocked:** Nothing.
