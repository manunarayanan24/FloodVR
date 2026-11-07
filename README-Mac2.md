# FloodVR - Mac 2 (phone-VR layer)

Authored outside Unity (no editor on this box yet). These are the 4 Mac 2 folders;
drop them into the real Unity project (Mac 1's repo, or a fresh Built-in 3D project).

## Contents
- Assets/Scripts/VR/           DamageItem (shared), HeadLook (gyro + mouse fallback)
- Assets/Scripts/VR/Editor/    VRRigBuilder, VRTestSceneBuilder, BuildWeb
- Assets/Plugins/WebGL/        DeviceOrientation.jslib (gyro -> Unity, iOS permission)
- Assets/WebGLTemplates/CardboardVR/  fullscreen template + PWA manifest

## Once Unity 6000.0.85f2 (+ WebGL module) is installed
1. Open/create the project, copy these folders into Assets/.
2. Player Settings: no action needed (BuildWeb sets compression/template).
3. Tools > FloodVR > Build VRTest Scene   (makes Assets/Scenes/VRTest.unity)
4. Press Play: mouse-look should work (split-screen two cameras).
5. Tools > FloodVR > Build Web  -> Builds/web
6. Serve over HTTPS / deploy (vercel). iPhone Safari -> Enter VR -> landscape stereo.

## Known on-device tweak
Head-tracking axis signs vary by phone. If look is mirrored/tilted, toggle
HeadLook.invertYaw / invertPitch on the Head object (no recompile of JS needed).

## Shared-type note
DamageItem.cs is a SHARED definition. If Mac 1 already defines DamageItem, delete
this copy to avoid a duplicate-type compile error.

## Not done yet
- Gaze selection (reticle + 1.5s dwell + world-space label + waterline readout)
- Swap BuildWeb's scene list to House.unity when Mac 1's scene lands
