# Mac 2 status (phone-VR layer)

**Done:** VR rig (two cameras, 0.064 m eye separation, 1.6 m eye height), head tracking, CardboardVR WebGL template + manifest, build menu.

**Done:** Head-tracking fix. The first version ignored the phone being held in landscape; `DeviceOrientation.jslib` now uses the three.js `DeviceOrientationControls` math (checked in Node: level landscape pose = horizontal view, heading turns left as alpha grows, +/-30 deg tilt = +/-0.5 vertical). `HeadLook` recentres yaw to the StandPoint direction once the phone is held level (or `window.floodVR.recenter()`).

**Done (round task 1):** `BuildWeb` never touches `House.unity`. It opens House, adds the rig in memory (`VRRigBuilder.EnsureRig`), saves a throw-away copy (`Assets/Scenes/_VRBuildTemp.unity`), builds the copy, reloads House from disk and deletes the copy. EnsureRig copies the scene camera's solid-colour sky onto the eye cameras, disables the scene's own camera + audio listener, and starts the rig at `StandPoint_Hallway`.

**Done (round task 3):** `GazeSelector` on the Head: 3D reticle + dwell ring, 1.5 s dwell, world-space label (label, category, severity, measuredValue + unit, note). Severity 0 shows "Undamaged". `heightAboveFloor` is shown if present (read by reflection until Mac 1's field lands; values <= 0.001 are treated as unset). Waterline shows "Water reached 0.90 m (2 ft 11 in)". Gazing the fridge sticky note shows its `scene_text`. Label text is rendered with rich text OFF (untrusted data).

**Done (round task 4):** `ApiConfig` reads the agents' base URL at runtime: `?api=` in the page URL first, then `StreamingAssets/config.json` (`{"apiBaseUrl": ""}`, new file). `ApiConfig.WhenReady(cb)` / `ApiConfig.Url("/callouts")` for the callouts + voice work.

**Doing:** First iPhone test of the deployed build, then StandPoint teleport. Build + deploy done; compiled clean in Unity 6000.0.85f2.

**Blocked:**
- Editor installed; Web Build Support being added (Windows Build Support was installed by mistake, harmless).
- None of the new C# has been compiled yet (no Unity on this machine until the install finishes). First compile happens when the project opens; expect to fix small typos then.

**Answered by Mac 1:** `heightAboveFloor` = float metres, floor to object bottom, 0 = unset (matches the <=0.001 rule). Sky copy + scene-camera disable already in EnsureRig. `config.json` approved. Teleport approved for after the first iPhone test.

**Waiting on others:**
- Abhinav: `/callouts` and `/voice` schemas in `contracts/` before headset callouts + tap-to-talk are built.

**Deploy URL:** https://web-gamma-three-xsqthicx3g.vercel.app (production alias, public, loads without login). Built headless (Build Web, 9.85 MB, Gzip). Not yet tested on an iPhone.

**Note for the deploy step:** use the short production alias (`https://<project>.vercel.app`) for the QR code. The long per-deployment URL can sit behind Vercel's login wall on some accounts, which would stop an iPhone at a sign-in page.
