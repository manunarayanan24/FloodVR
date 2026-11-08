using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace FloodVR
{
    public static class SceneStats
    {
        [MenuItem("Tools/FloodVR/Report Scene Stats")]
        public static void Report()
        {
            if (!DamageBuilder.EnsureHouseSceneOpen()) return;

            MeshRenderer[] renderers = UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                .Where(r => r.enabled && r.gameObject.activeInHierarchy)
                .ToArray();

            long totalTris = 0;
            // Static-batched renderers sharing a material collapse into one
            // batch; everything else (non-static, or no renderer) costs its
            // own. This mirrors what StaticBatchingUtility does at build
            // time -- it's an analytical count, not a live GPU profiler
            // capture (batchmode has no rendered frame to read stats from).
            var staticBatchGroups = new HashSet<string>();
            int dynamicBatches = 0;

            foreach (MeshRenderer rend in renderers)
            {
                MeshFilter mf = rend.GetComponent<MeshFilter>();
                if (mf != null && mf.sharedMesh != null) totalTris += mf.sharedMesh.triangles.Length / 3;

                bool isStatic = GameObjectUtility.AreStaticEditorFlagsSet(rend.gameObject, StaticEditorFlags.BatchingStatic);
                Material mat = rend.sharedMaterial;
                string matKey = mat != null ? mat.GetInstanceID().ToString() : "null";

                if (isStatic) staticBatchGroups.Add(matKey);
                else dynamicBatches++;
            }

            int estimatedBatches = staticBatchGroups.Count + dynamicBatches;
            int materialCount = renderers.Select(r => r.sharedMaterial).Where(m => m != null).Distinct().Count();

            string report =
                $"[FloodVR] Scene stats -- renderers: {renderers.Length}, triangles: {totalTris}, " +
                $"distinct materials: {materialCount}, estimated batches: {estimatedBatches} " +
                $"({staticBatchGroups.Count} static groups + {dynamicBatches} dynamic/non-static) | " +
                $"targets: <150 batches, <100k tris -> {(estimatedBatches < 150 ? "PASS" : "FAIL")} batches, " +
                $"{(totalTris < 100000 ? "PASS" : "FAIL")} tris";

            Debug.Log(report);
        }
    }
}
