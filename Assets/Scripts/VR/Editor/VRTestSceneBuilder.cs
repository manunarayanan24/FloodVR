#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace FloodVR.EditorTools
{
    // Builds Assets/Scenes/VRTest.unity: floor, a few DamageItem cubes, a waterline,
    // and the VR rig. Stand-in until Mac 1's House scene arrives.
    public static class VRTestSceneBuilder
    {
        [MenuItem("Tools/FloodVR/Build VRTest Scene")]
        public static void Build()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = "Floor";
            floor.transform.localScale = new Vector3(1.2f, 1f, 1.2f);

            Cube("FridgeTipped",   new Vector3(-2f, 0.9f,  3f), new Vector3(0.9f,1.8f,0.9f),
                 "contents", 4, 0f, "", "Fridge tipped over");
            Cube("CabinetSwollen", new Vector3( 2f, 0.45f, 3f), new Vector3(1.2f,0.9f,0.6f),
                 "flood", 3, 0.9f, "m", "Swollen base cabinets");
            Cube("CeilingStain",   new Vector3( 0f, 2.4f,  4f), new Vector3(1f,0.05f,1f),
                 "wind", 2, 0f, "", "Ceiling stain ABOVE waterline = wind/rain peril");
            Cube("WallCrack",      new Vector3(-3f, 1.3f,  0f), new Vector3(0.05f,1.5f,1.2f),
                 "structural", 3, 0f, "", "Hallway wall crack");

            // Waterline marker at 0.90 m
            var wl = GameObject.CreatePrimitive(PrimitiveType.Cube);
            wl.name = "Waterline_0.90m";
            wl.transform.position = new Vector3(0f, 0.9f, 3f);
            wl.transform.localScale = new Vector3(8f, 0.01f, 8f);

            VRRigBuilder.AddRig();

            const string dir = "Assets/Scenes";
            if (!AssetDatabase.IsValidFolder(dir)) AssetDatabase.CreateFolder("Assets", "Scenes");
            EditorSceneManager.SaveScene(scene, dir + "/VRTest.unity");
            Debug.Log("[FloodVR] VRTest scene built and saved.");
        }

        static void Cube(string name, Vector3 pos, Vector3 scale, string cat,
                         int severity, float measured, string unit, string note)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.name = name;
            go.transform.position = pos;
            go.transform.localScale = scale;
            var d = go.AddComponent<DamageItem>();
            d.id = name; d.label = name; d.category = cat; d.severity = severity;
            d.measuredValue = measured; d.unit = unit; d.note = note;
        }
    }
}
#endif
