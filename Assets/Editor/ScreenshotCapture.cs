using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace FloodVR
{
    [Serializable]
    public class ScreenEntry
    {
        public string filename;
        public string standpoint;
        public Vec3Data position;
        public float yaw;
        public float pitch;
        public float fov;
        public string[] visibleDamageIds;
        public string[] visibleSceneTextIds;
    }

    [Serializable]
    public class ScreensManifest
    {
        public ScreenEntry[] screens;
    }

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

            DamageItem[] allDamageItems = UnityEngine.Object.FindObjectsByType<DamageItem>(FindObjectsSortMode.None);
            SceneText[] allSceneTexts = UnityEngine.Object.FindObjectsByType<SceneText>(FindObjectsSortMode.None);

            List<ScreenEntry> screenEntries = new();
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

                    Vector3 euler = camGO.transform.eulerAngles;
                    float pitch = euler.x > 180f ? euler.x - 360f : euler.x;

                    screenEntries.Add(new ScreenEntry
                    {
                        filename = fileName,
                        standpoint = spId,
                        position = new Vec3Data { x = camGO.transform.position.x, y = camGO.transform.position.y, z = camGO.transform.position.z },
                        yaw = euler.y,
                        pitch = pitch,
                        fov = cam.fieldOfView,
                        visibleDamageIds = allDamageItems.Where(d => IsVisible(cam, d.transform)).Select(d => d.id).OrderBy(id => id).ToArray(),
                        visibleSceneTextIds = allSceneTexts.Where(s => IsVisible(cam, s.transform)).Select(s => s.id).OrderBy(id => id).ToArray(),
                    });
                }
            }

            cam.targetTexture = null;
            rt.Release();
            UnityEngine.Object.DestroyImmediate(tex);
            UnityEngine.Object.DestroyImmediate(camGO);

            string screensJsonPath = Path.Combine(screensDir, "screens.json");
            string screensJson = JsonUtility.ToJson(new ScreensManifest { screens = screenEntries.ToArray() }, true);
            File.WriteAllText(screensJsonPath, screensJson);

            DamageBuilder.ExportDamageManifest();
            string manifestSrc = Path.Combine(Application.dataPath, "StreamingAssets/damage_manifest.json");
            string manifestDest = Path.Combine(repoRoot, "contracts", "samples", "house_manifest.json");
            if (File.Exists(manifestSrc)) File.Copy(manifestSrc, manifestDest, true);

            Debug.Log($"[FloodVR] Captured {shotCount} screenshots + screens.json answer key to contracts/samples/screens/, copied manifest to contracts/samples/house_manifest.json");
        }

        // In-frustum (viewport test) AND not occluded by anything closer (raycast),
        // excluding the target's own collider (and its children/parents) so an
        // object doesn't register as blocking the ray to its own position.
        private static bool IsVisible(Camera cam, Transform target)
        {
            Vector3 worldPos = target.position;
            Vector3 viewport = cam.WorldToViewportPoint(worldPos);
            bool inFrustum = viewport.z > 0f && viewport.x >= 0f && viewport.x <= 1f && viewport.y >= 0f && viewport.y <= 1f;
            if (!inFrustum) return false;

            Vector3 toTarget = worldPos - cam.transform.position;
            float distance = toTarget.magnitude;
            if (distance < 0.001f) return true;

            RaycastHit[] hits = Physics.RaycastAll(cam.transform.position, toTarget.normalized, distance - 0.02f);
            foreach (RaycastHit hit in hits)
            {
                Transform hitT = hit.transform;
                if (hitT == target || hitT.IsChildOf(target) || target.IsChildOf(hitT)) continue; // self, not a real blocker
                return false;
            }
            return true;
        }
    }
}
