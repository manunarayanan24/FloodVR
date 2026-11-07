using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace FloodVR
{
    public static class ScreenshotCapture
    {
        private const int Width = 1280;
        private const int Height = 720;
        private static readonly float[] YawOffsets = { -30f, 0f, 30f };
        private static readonly string[] StandPointIds = { "StandPoint_Hallway", "StandPoint_Living", "StandPoint_Kitchen" };

        [MenuItem("Tools/FloodVR/Capture Screens")]
        public static void CaptureScreens()
        {
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
            {
                Debug.LogError("[FloodVR] Capture Screens needs real rendering -- run batchmode WITHOUT -nographics.");
                return;
            }

            if (!DamageBuilder.EnsureHouseSceneOpen()) return;

            string repoRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string screensDir = Path.Combine(repoRoot, "contracts", "samples", "screens");
            Directory.CreateDirectory(screensDir);

            GameObject camGO = new GameObject("ScreenshotCamera");
            Camera cam = camGO.AddComponent<Camera>();
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 100f;
            cam.fieldOfView = 60f;
            if (Camera.main != null)
            {
                cam.clearFlags = Camera.main.clearFlags;
                cam.backgroundColor = Camera.main.backgroundColor;
            }
            else
            {
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = RenderSettings.fogColor;
            }

            RenderTexture rt = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
            cam.targetTexture = rt;
            Texture2D tex = new Texture2D(Width, Height, TextureFormat.RGB24, false);

            int shotCount = 0;
            foreach (string spId in StandPointIds)
            {
                Transform sp = GameObject.Find(spId)?.transform;
                if (sp == null)
                {
                    Debug.LogWarning($"[FloodVR] StandPoint '{spId}' not found, skipping.");
                    continue;
                }

                for (int i = 0; i < YawOffsets.Length; i++)
                {
                    camGO.transform.position = sp.position;
                    camGO.transform.rotation = Quaternion.Euler(0f, YawOffsets[i], 0f) * sp.rotation;

                    cam.Render();
                    RenderTexture.active = rt;
                    tex.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                    tex.Apply();
                    RenderTexture.active = null;

                    byte[] png = tex.EncodeToPNG();
                    string fileName = $"{spId}_{i}.png";
                    File.WriteAllBytes(Path.Combine(screensDir, fileName), png);
                    shotCount++;
                }
            }

            cam.targetTexture = null;
            rt.Release();
            Object.DestroyImmediate(tex);
            Object.DestroyImmediate(camGO);

            DamageBuilder.ExportDamageManifest();
            string manifestSrc = Path.Combine(Application.dataPath, "StreamingAssets/damage_manifest.json");
            string manifestDest = Path.Combine(repoRoot, "contracts", "samples", "house_manifest.json");
            if (File.Exists(manifestSrc)) File.Copy(manifestSrc, manifestDest, true);

            Debug.Log($"[FloodVR] Captured {shotCount} screenshots to contracts/samples/screens/ and copied manifest to contracts/samples/house_manifest.json");
        }
    }
}
