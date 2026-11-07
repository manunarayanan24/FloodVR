using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace FloodVR
{
    public static class TmpSetup
    {
        [MenuItem("Tools/FloodVR/Import TMP Essentials")]
        public static void ImportEssentials()
        {
            string packageCacheDir = Path.Combine(Application.dataPath, "../Library/PackageCache");
            string[] matches = Directory.Exists(packageCacheDir)
                ? Directory.GetDirectories(packageCacheDir, "com.unity.ugui@*")
                : new string[0];

            if (matches.Length == 0)
            {
                Debug.LogError("[FloodVR] com.unity.ugui package not found in PackageCache. Open the project once so Package Manager can resolve dependencies, then retry.");
                return;
            }

            string essentialsPath = Path.Combine(matches[0], "Package Resources/TMP Essential Resources.unitypackage");
            if (!File.Exists(essentialsPath))
            {
                Debug.LogError($"[FloodVR] TMP Essential Resources.unitypackage not found at {essentialsPath}");
                return;
            }

            AssetDatabase.ImportPackage(essentialsPath, false);
            Debug.Log("[FloodVR] TMP Essential Resources import started.");

            if (Application.isBatchMode)
            {
                double start = EditorApplication.timeSinceStartup;
                EditorApplication.update += () => PollForCompletion(start);
            }
        }

        private static void PollForCompletion(double start)
        {
            bool done = AssetDatabase.IsValidFolder("Assets/TextMesh Pro/Resources");
            bool timedOut = EditorApplication.timeSinceStartup - start > 60.0;
            if (done)
            {
                Debug.Log("[FloodVR] TMP Essential Resources import complete.");
                EditorApplication.Exit(0);
            }
            else if (timedOut)
            {
                Debug.LogError("[FloodVR] TMP Essential Resources import timed out.");
                EditorApplication.Exit(1);
            }
        }
    }
}
