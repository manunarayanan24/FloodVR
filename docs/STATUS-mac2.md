# Mac 2 status (phone-VR layer)

**Done:** VR rig (two cameras, 0.064 m eye separation, 1.6 m eye height), head tracking, CardboardVR WebGL template + manifest, build menu.

**Done:** Head-tracking fix. The first version ignored the phone being held in landscape; `DeviceOrientation.jslib` now uses the three.js `DeviceOrientationControls` math (checked in Node: level landscape pose = horizontal view, heading turns left as alpha grows, +/-30 deg tilt = +/-0.5 vertical). `HeadLook` recentres yaw to the StandPoint direction once the phone is held level (or `window.floodVR.recenter()`).

**Done (round task 1):** `BuildWeb` never touches `House.unity`. It opens House, adds the rig in memory (`VRRigBuilder.EnsureRig`), saves a throw-away copy (`Assets/Scenes/_VRBuildTemp.unity`), builds the copy, reloads House from disk and deletes the copy. EnsureRig copies the scene camera's solid-colour sky onto the eye cameras, disables the scene's own camera + audio listener, and starts the rig at `StandPoint_Hallway`.

**Done (round task 3):** `GazeSelector` on the Head: 3D reticle + dwell ring, 1.5 s dwell, world-space label (label, category, severity, measuredValue + unit, note). Severity 0 shows "Undamaged". `heightAboveFloor` is shown if present (read by reflection until Mac 1's field lands; values <= 0.001 are treated as unset). Waterline shows "Water reached 0.90 m (2 ft 11 in)". Gazing the fridge sticky note shows its `scene_text`. Label text is rendered with rich text OFF (untrusted data).

**Done (round task 4):** `ApiConfig` reads the agents' base URL at runtime: `?api=` in the page URL first, then `StreamingAssets/config.json` (`{"apiBaseUrl": ""}`, new file). `ApiConfig.WhenReady(cb)` / `ApiConfig.Url("/callouts")` for the callouts + voice work.

**Done:** Build compiled clean, deployed, iPhone-tested end to end. Stereo view and head tracking work. Gaze labels auto-fit the panel. Walk-between-StandPoints by gazing at blue beams (visible through walls), glides over 1-2 s with a comfort fade. Headset callouts (`/callouts`) show 16 real server callouts (6 red hazards, amber "Injection caught" on the fridge note, blue waterline + flood-cut area, green undamaged laptop/electronics). Offline sample callouts still bundled as a venue-wifi safety net. LiveKit voice integrated using Abhinav's `/voice/client.js`, `FloodVRVoice.jslib`, `LiveKitVoice.cs`; tap once to open the mic, tap again to send; "You said" + "Agent" captions on the HUD; NVIDIA Magpie speaks the reply. Safari speech recognition kept as fallback. Tested on an iPhone in the cardboard viewer: all four features work end to end.

**Done (2026-11-08 morning):** Repointed `StreamingAssets/config.json` at Abhinav's new tunnel `https://achieve-custom-pressed-ellen.trycloudflare.com` (the old `starter-king-jackson-avon` died while his PC slept). Flagged by lead in README section 9. Fresh phones will now get live callouts + voice without needing `?api=...`. Awaiting rebuild + redeploy.

**Next:** Rebuild + redeploy (`bash ~/ship.sh`) then re-test on the iPhone. Also: after Mac 1's visual pass lands, rebuild + redeploy again + re-test.

**Done (2026-11-08, visual pass round):** Picked up Mac 1's visual polish (Poly Haven textures + CC0 furniture, warmer lighting, fridge note close-up, House.unity regenerated) — no code change needed, just rebuild + redeploy.

**Done (2026-11-08, open-mic voice):** Per Windows' request in `contracts/voice_unity/README.md`, VoiceClient.Start() now also calls `_lk.Connect()` via ApiConfig.WhenReady (OnEnteredVR retries from the Enter VR gesture). Ready text is "Voice ready - just talk"; mic-blocked errors show "Microphone blocked - allow the mic and reload". setMic() is a server-side no-op now so the existing tap-toggle in `DeviceOrientation.jslib` is harmless.

**Next:** Rebuild + redeploy (`bash ~/ship.sh`), then iPhone-test: enter VR, allow mic, say "How high did the water get?", wait; captions + spoken answer should appear with no tap.

**Done (2026-11-08 later, on iPhone feedback):** Confirmed open-mic LiveKit voice works end to end on the iPhone (just talk, agent replies, captions on the HUD). User reported gliding between rooms stopped working after Mac 1's visual pass (new furniture mesh colliders block the thin beam gaze column). Enlarged `StandPointNav` beam BoxCollider from world 0.4x1.6x0.4 to 1.2x3x1.2 m so beams remain hit-able across crowded rooms. Awaiting rebuild + retest.

**Blocked:** Nothing. All of Mac 2's lane is done.

**Waiting on others:**
- Nothing outstanding. (`GET /callouts` live - 16 callouts; LiveKit voice live; iPhone-tested.)

**Deploy URL:** https://web-gamma-three-xsqthicx3g.vercel.app (production alias, public, loads without login). Built headless (Build Web, 9.85 MB, Gzip). Not yet tested on an iPhone.

**Note for the deploy step:** use the short production alias (`https://<project>.vercel.app`) for the QR code. The long per-deployment URL can sit behind Vercel's login wall on some accounts, which would stop an iPhone at a sign-in page.
