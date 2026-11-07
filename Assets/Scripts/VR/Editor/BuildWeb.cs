#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace FloodVR.EditorTools
{
    public static class BuildWeb
    {
        const string HouseScenePath = "Assets/Scenes/House.unity";
        // A throw-away COPY of House with the VR rig added. Deleted right after the build.
        const string TempScenePath = "Assets/Scenes/_VRBuildTemp.unity";

        [MenuItem("Tools/FloodVR/Build Web")]
        public static void Build()
        {
            if (!File.Exists(HouseScenePath))
            {
                Debug.LogError("[FloodVR] " + HouseScenePath + " not found. Run Mac 1's Tools > FloodVR > Build House first.");
                return;
            }
            // Never lose someone's unsaved work (and never save the rig by accident).
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                Debug.LogWarning("[FloodVR] Web build cancelled.");
                return;
            }

            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
            PlayerSettings.WebGL.decompressionFallback = true;
            PlayerSettings.WebGL.template = "PROJECT:CardboardVR";
            PlayerSettings.runInBackground = true;
            QualitySettings.SetQualityLevel(0, true); // low

            string outDir = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "Builds", "web");
            Directory.CreateDirectory(outDir);

            BuildReport report = null;
            try
            {
                // Open House from disk, add the rig in memory only, save a COPY, build the copy.
                // House.unity itself is never modified, so Mac 1 can regenerate it at will.
                var house = EditorSceneManager.OpenScene(HouseScenePath, OpenSceneMode.Single);
                VRRigBuilder.EnsureRig();
                if (!EditorSceneManager.SaveScene(house, TempScenePath, true))
                    throw new Exception("could not write temporary scene " + TempScenePath);
                AssetDatabase.ImportAsset(TempScenePath);

                var opts = new BuildPlayerOptions
                {
                    scenes = new[] { TempScenePath },
                    locationPathName = outDir,
                    target = BuildTarget.WebGL,
                    options = BuildOptions.None
                };
                report = BuildPipeline.BuildPlayer(opts);
            }
            catch (Exception e)
            {
                Debug.LogError("[FloodVR] Web build aborted: " + e);
            }
            finally
            {
                // Reload House from disk: throws away the in-memory rig. Remove the temp copy.
                if (File.Exists(HouseScenePath))
                    EditorSceneManager.OpenScene(HouseScenePath, OpenSceneMode.Single);
                AssetDatabase.DeleteAsset(TempScenePath);
            }

            if (report != null && report.summary.result == BuildResult.Succeeded)
                Debug.Log("[FloodVR] Web build OK -> " + outDir + "  (" + report.summary.totalSize + " bytes)");
            else if (report != null)
                Debug.LogError("[FloodVR] Web build FAILED: " + report.summary.result);
        }
    }
}
#endif
