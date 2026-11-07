#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace FloodVR.EditorTools
{
    public static class BuildWeb
    {
        [MenuItem("Tools/FloodVR/Build Web")]
        public static void Build()
        {
            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
            PlayerSettings.WebGL.decompressionFallback = true;
            PlayerSettings.WebGL.template = "PROJECT:CardboardVR";
            PlayerSettings.runInBackground = true;
            QualitySettings.SetQualityLevel(0, true); // low

            string outDir = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "Builds", "web");
            Directory.CreateDirectory(outDir);

            var scenes = new[] { "Assets/Scenes/House.unity" }; // Mac 1 house scene
            var opts = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = outDir,
                target = BuildTarget.WebGL,
                options = BuildOptions.None
            };

            BuildReport report = BuildPipeline.BuildPlayer(opts);
            if (report.summary.result == BuildResult.Succeeded)
                Debug.Log("[FloodVR] Web build OK -> " + outDir + "  (" + report.summary.totalSize + " bytes)");
            else
                Debug.LogError("[FloodVR] Web build FAILED: " + report.summary.result);
        }
    }
}
#endif
