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
            // CoffeeTable_01 tried and reverted: its footprint-fit scaling
            // produced a visibly broken orientation (narrow/tall instead of
            // low/wide) within this time-boxed pass -- left as the original
            // primitive rather than ship something that looks wrong.
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

                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
                if (prefab == null)
                {
                    Debug.LogWarning($"[FloodVR] model not found at '{modelPath}' for '{furnitureId}'.");
                    continue;
                }

                FitModelToPrimitive(original, prefab, yRotOffset);
            }
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

            Vector3 nativeSize = bounds.Value.size;
            float footprintScale = Mathf.Min(
                nativeSize.x > 0.001f ? targetSize.x / nativeSize.x : 1f,
                nativeSize.z > 0.001f ? targetSize.z / nativeSize.z : 1f);
            instance.transform.localScale = Vector3.one * footprintScale;

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
