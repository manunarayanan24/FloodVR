using UnityEditor;
using UnityEngine;

namespace FloodVR
{
    // Swaps a primitive furniture box's VISUAL for a CC0 model, without
    // touching the original GameObject's id, position, collider or any
    // DamageItem/FloodVisual component attached to it later -- the
    // primitive's own MeshRenderer is just disabled, and the model goes in
    // as a child, scaled to roughly fit the primitive's original footprint.
    public static class FurnitureModelBuilder
    {
        private static readonly (string furnitureId, string modelPath, float yRotOffset)[] Replacements =
        {
            ("sofa", "Assets/ThirdParty/PolyHaven/Models/Sofa_01.fbx", 90f),
            ("bookshelf", "Assets/ThirdParty/PolyHaven/Models/Shelf_01.fbx", 90f),
            ("kitchen_chair_1", "Assets/ThirdParty/PolyHaven/Models/WoodenChair_01.fbx", 0f),
            ("kitchen_chair_2", "Assets/ThirdParty/PolyHaven/Models/WoodenChair_01.fbx", 0f),
            // CoffeeTable_01: fixed a real bug (useFileScale was misreading
            // these Poly Haven FBX exports as centimeters, shrinking every
            // model 100x) but this specific model's mesh content is also
            // off-center from its own pivot, which the fitter doesn't
            // correct for -- still renders wrong. Reverted again rather than
            // debug pivot correction within this time box; left as the
            // primitive. Worth a per-model pivot offset in a future pass.
        };

        public static void ReplaceVisuals()
        {
            foreach (var (furnitureId, modelPath, yRotOffset) in Replacements)
            {
                GameObject original = GameObject.Find(furnitureId);
                if (original == null)
                {
                    Debug.LogWarning($"[FloodVR] furniture '{furnitureId}' not found for model swap.");
                    continue;
                }

                GameObject prefab = LoadModelWithCorrectScale(modelPath);
                if (prefab == null)
                {
                    Debug.LogWarning($"[FloodVR] model not found at '{modelPath}' for '{furnitureId}'.");
                    continue;
                }

                FitModelToPrimitive(original, prefab, yRotOffset);
            }
        }

        // These Poly Haven FBX exports come in with Unity's default import
        // scale (0.01), which leaves them ~100x too small -- the footprint
        // ratio math still converges on roughly the right size most of the
        // time, but inflates floating point error and, for at least one
        // model, produced a visibly wrong aspect. Fix it at the source so
        // the model's bounds are close to its real-world size before any
        // fitting math runs.
        private static GameObject LoadModelWithCorrectScale(string path)
        {
            ModelImporter importer = AssetImporter.GetAtPath(path) as ModelImporter;
            if (importer != null && importer.useFileScale)
            {
                // Unity auto-detected these Poly Haven FBX exports as
                // centimeters (fileScale 0.01), shrinking every model 100x.
                // They're actually authored in meters -- ignore the file's
                // embedded unit metadata and trust raw vertex coordinates.
                importer.useFileScale = false;
                importer.SaveAndReimport();
            }
            return AssetDatabase.LoadAssetAtPath<GameObject>(path);
        }

        private static void FitModelToPrimitive(GameObject original, GameObject prefab, float yRotOffset)
        {
            Renderer primitiveRenderer = original.GetComponent<Renderer>();
            Vector3 targetSize = original.transform.localScale; // the primitive's authored box dimensions, in meters

            // Wrapper whose local space == world meters, regardless of the
            // original's (possibly non-uniform) scale -- same trick used for
            // the fridge's sticky note.
            GameObject wrapper = new GameObject($"{original.name}_ModelWrapper");
            wrapper.transform.SetParent(original.transform, false);
            wrapper.transform.localScale = new Vector3(1f / targetSize.x, 1f / targetSize.y, 1f / targetSize.z);

            GameObject instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, wrapper.transform);
            instance.transform.localPosition = Vector3.zero;
            instance.transform.localRotation = Quaternion.Euler(0f, yRotOffset, 0f);
            instance.transform.localScale = Vector3.one;

            Bounds? bounds = GetRendererBounds(instance);
            if (bounds == null)
            {
                Debug.LogWarning($"[FloodVR] model for '{original.name}' has no renderers, leaving primitive visible.");
                Object.DestroyImmediate(wrapper);
                return;
            }

            // Min across ALL three axes (not just footprint x/z) -- a model's
            // real-world proportions don't necessarily match the primitive
            // box's authored aspect ratio (e.g. a side-table-height model
            // standing in for a low coffee table), so fitting x/z alone can
            // leave it taller than the room expects. Taking the min guarantees
            // the model never overflows the target box in any dimension.
            Vector3 nativeSize = bounds.Value.size;
            float scale = Mathf.Min(
                nativeSize.x > 0.001f ? targetSize.x / nativeSize.x : 1f,
                Mathf.Min(
                    nativeSize.y > 0.001f ? targetSize.y / nativeSize.y : 1f,
                    nativeSize.z > 0.001f ? targetSize.z / nativeSize.z : 1f));
            instance.transform.localScale = Vector3.one * scale;

            // Re-measure after scaling and shift so the model's lowest point
            // sits on the primitive's original base (bottom of its box).
            Bounds scaledBounds = GetRendererBounds(instance).Value;
            float worldBottom = scaledBounds.min.y;
            float targetBottomWorld = original.transform.position.y - targetSize.y / 2f;
            float deltaWorldY = targetBottomWorld - worldBottom;
            // wrapper local space is world-meters, so a world-Y delta maps 1:1 to wrapper-local Y
            instance.transform.localPosition += new Vector3(0f, deltaWorldY, 0f);

            // Keep the original box around for its collider/DamageItem/id, just hide its visual.
            if (primitiveRenderer != null) primitiveRenderer.enabled = false;

            // Give the model the PRIMITIVE's own flat-color material (not the
            // FBX's own imported one) -- this is what keeps the model visually
            // consistent with the rest of the flat-shaded scene, AND is what
            // makes DamageBuilder's color mutations (darkenFurniture etc,
            // which recolor go.GetComponent<Renderer>().sharedMaterial on the
            // now-invisible primitive) still show up: the model's renderer
            // shares that exact same material object.
            foreach (Renderer r in instance.GetComponentsInChildren<Renderer>())
            {
                if (primitiveRenderer != null) r.sharedMaterial = primitiveRenderer.sharedMaterial;
                HouseBuilder.MarkBatchingStatic(r.gameObject);
            }
        }

        private static Bounds? GetRendererBounds(GameObject root)
        {
            Renderer[] renderers = root.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return null;
            Bounds b = renderers[0].bounds;
            for (int i = 1; i < renderers.Length; i++) b.Encapsulate(renderers[i].bounds);
            return b;
        }
    }
}
