# Mac 2 - phone-VR layer (notes)

Owner notes for the stereo / head-tracking / gaze / build layer. The team README is `README.md`
(Mac 1 owns it). Status lives in `docs/STATUS-mac2.md`.

## What is here (all under my lanes)
- `Assets/Scripts/VR/HeadLook.cs` - camera orientation from the phone (landscape-corrected), editor mouse-look fallback, auto/manual recenter.
- `Assets/Scripts/VR/GazeSelector.cs` - reticle, 1.5 s dwell, world-space label, waterline readout, fridge note.
- `Assets/Scripts/VR/ApiConfig.cs` - runtime agents URL (`?api=` / `StreamingAssets/config.json`).
- `Assets/Scripts/VR/Editor/VRRigBuilder.cs` - `Tools > FloodVR > Add VR Rig to Active Scene` + `EnsureRig()` used by the build.
- `Assets/Scripts/VR/Editor/BuildWeb.cs` - `Tools > FloodVR > Build Web` -> `Builds/web`.
- `Assets/Scripts/VR/Editor/VRTestSceneBuilder.cs` - `Tools > FloodVR > Build VRTest Scene` (standalone test scene).
- `Assets/Plugins/WebGL/DeviceOrientation.jslib` - gyro bridge, iOS permission, query-param reader.
- `Assets/WebGLTemplates/CardboardVR/` - fullscreen template, rotate-to-landscape gate, "Enter VR" tap, wake lock.
- `Assets/StreamingAssets/config.json` - `{"apiBaseUrl": ""}` (new file; Mac 1's manifest is untouched).

## Rules I follow
- The VR rig is never saved into `House.unity`. `BuildWeb` adds it to an in-memory copy.
- All my editor scripts stay in `Assets/Scripts/VR/Editor/` (`Assets/Editor/` is Mac 1's).
- Untrusted text (notes, scene text) is shown with rich text off.

## First iPhone test (after the first deploy)
1. iPhone Safari -> the Vercel URL (the short `<project>.vercel.app` alias).
2. Share -> Add to Home Screen, then launch it from the Home Screen.
3. Turn the phone to landscape. Tap "Enter VR" and allow Motion & Orientation.
4. Put the phone in the viewer. Hold it level for a second: that heading becomes "straight ahead".
5. Check: two side-by-side views; turning your head left turns the view left; looking up looks up; the world does not drift or tilt.
6. Look at the fridge or the cabinet for 1.5 s: a label should appear above the reticle.

## If head tracking is off on the device
Select `Head` in the rig and tick `invertYaw` / `invertPitch` on `HeadLook`; or edit the sign of the conversion in `HeadLook.OnDeviceQuaternion`. Report which one fixed it.

## Changing the agents URL without a rebuild
- Open the page with `?api=https://your-tunnel` (works in Safari; iOS gives a Home Screen app separate storage, so it may not carry over), or
- edit `Builds/web/StreamingAssets/config.json` and run `vercel deploy Builds/web --prod --yes` again.
