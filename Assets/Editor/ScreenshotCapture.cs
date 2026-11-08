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
                    cam.fieldOfView = 60f;

                    screenEntries.Add(CaptureOne(cam, camGO, tex, rt, screensDir, $"{spId}_{i}.png", spId, allDamageItems, allSceneTexts));
                    shotCount++;
                }
            }

            // Dedicated close-up on the fridge note: framed from the note's own
            // current world transform, so it stays correct whether the fridge
            // is upright (pre-flood) or tipped over (post-flood).
            Transform noteCard = GameObject.Find("SceneText_fridge_sticky_note_Card")?.transform;
            if (noteCard != null)
            {
                camGO.transform.position = noteCard.position + noteCard.forward * 0.75f;
                camGO.transform.rotation = Quaternion.LookRotation(-noteCard.forward, noteCard.up);
                cam.fieldOfView = 40f;

                screenEntries.Add(CaptureOne(cam, camGO, tex, rt, screensDir, "StandPoint_Kitchen_note.png", "StandPoint_Kitchen_note", allDamageItems, allSceneTexts));
                shotCount++;
            }
            else
            {
                Debug.LogWarning("[FloodVR] fridge sticky note card not found, skipping close-up capture.");
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

        private static ScreenEntry CaptureOne(Camera cam, GameObject camGO, Texture2D tex, RenderTexture rt,
            string screensDir, string fileName, string standpointLabel, DamageItem[] allDamageItems, SceneText[] allSceneTexts)
        {
            cam.Render();
            RenderTexture.active = rt;
            tex.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            tex.Apply();
            RenderTexture.active = null;

            byte[] png = tex.EncodeToPNG();
            File.WriteAllBytes(Path.Combine(screensDir, fileName), png);

            Vector3 euler = camGO.transform.eulerAngles;
            float pitch = euler.x > 180f ? euler.x - 360f : euler.x;

            return new ScreenEntry
            {
                filename = fileName,
                standpoint = standpointLabel,
                position = new Vec3Data { x = camGO.transform.position.x, y = camGO.transform.position.y, z = camGO.transform.position.z },
                yaw = euler.y,
                pitch = pitch,
                fov = cam.fieldOfView,
                visibleDamageIds = allDamageItems.Where(d => IsVisible(cam, d.transform)).Select(d => d.id).OrderBy(id => id).ToArray(),
                visibleSceneTextIds = allSceneTexts.Where(s => IsVisible(cam, s.transform)).Select(s => s.id).OrderBy(id => id).ToArray(),
            };
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
