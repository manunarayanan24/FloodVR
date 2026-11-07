#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

namespace FloodVR.EditorTools
{
    // Adds the split-screen stereo rig to whatever scene is open.
    // Run this on Mac 1's House scene once it lands, and it's used by the VRTest builder.
    public static class VRRigBuilder
    {
        const float EyeSeparation = 0.064f; // metres
        const float EyeHeight     = 1.6f;   // metres

        [MenuItem("Tools/FloodVR/Add VR Rig to Active Scene")]
        public static GameObject AddRig()
        {
            var root = new GameObject("VRRig");
            Undo.RegisterCreatedObjectUndo(root, "Add VR Rig");

            var stand = new GameObject("StandPoint");          // where the adjuster stands
            stand.transform.SetParent(root.transform, false);

            var head = new GameObject("Head");
            head.transform.SetParent(root.transform, false);
            head.transform.localPosition = new Vector3(0f, EyeHeight, 0f);
            head.AddComponent<HeadLook>();
            head.AddComponent<AudioListener>();

            MakeEye(head.transform, "LeftEye",  -EyeSeparation * 0.5f, new Rect(0f,   0f, 0.5f, 1f), 1);
            MakeEye(head.transform, "RightEye",  EyeSeparation * 0.5f, new Rect(0.5f, 0f, 0.5f, 1f), 2);

            Selection.activeGameObject = root;
            Debug.Log("[FloodVR] VR rig added. Head carries HeadLook; eyes split 0-0.5 / 0.5-1.");
            return root;
        }

        static void MakeEye(Transform head, string name, float xOffset, Rect rect, int depth)
        {
            var go = new GameObject(name);
            go.transform.SetParent(head, false);
            go.transform.localPosition = new Vector3(xOffset, 0f, 0f);
            var cam = go.AddComponent<Camera>();
            cam.rect = rect;
            cam.depth = depth;
            cam.nearClipPlane = 0.05f;
            cam.fieldOfView = 70f;
        }
    }
}
#endif
