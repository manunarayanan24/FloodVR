using UnityEditor;
using UnityEngine;
using TMPro;

namespace FloodVR
{
    public static class SceneTextBuilder
    {
        private const string FontAssetPath = "Assets/TextMesh Pro/Resources/Fonts & Materials/LiberationSans SDF.asset";

        public static void BuildSceneTexts(HouseLayout layout)
        {
            if (layout.sceneTexts == null) return;

            foreach (SceneTextData st in layout.sceneTexts)
            {
                GameObject target = GameObject.Find(st.targetId);
                if (target == null)
                {
                    Debug.LogWarning($"[FloodVR] sceneText target '{st.targetId}' not found for '{st.id}'");
                    continue;
                }
                BuildStickyNote(target.transform, st);
            }
        }

        // Builds a yellow note card + readable 3D TextMeshPro text, parented to
        // the target furniture. Local scale/position are compensated against the
        // parent's (possibly non-uniform) scale so the note reads correctly in
        // world space regardless of the parent's own scale or rotation (e.g. a
        // tipped-over fridge in the post-flood state).
        private static void BuildStickyNote(Transform parent, SceneTextData st)
        {
            Vector3 parentScale = parent.localScale;
            Vector3 localPos = new Vector3(0f, 0.1f, 0.505f);

            GameObject card = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"SceneText_{st.id}_Card", parent);
            card.transform.localPosition = localPos;
            card.transform.localRotation = Quaternion.identity;
            Vector3 cardWorldSize = new Vector3(0.3f, 0.22f, 0.01f);
            card.transform.localScale = new Vector3(
                cardWorldSize.x / parentScale.x,
                cardWorldSize.y / parentScale.y,
                cardWorldSize.z / parentScale.z);
            card.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(new Color(1f, 0.92f, 0.3f), $"{st.id}_card");

            GameObject textGO = new GameObject($"SceneText_{st.id}_Text");
            textGO.transform.SetParent(parent, false);
            textGO.transform.localPosition = localPos + new Vector3(0f, 0f, 0.01f);
            // TMP's default glyph quad faces -Z; rotate so it reads correctly
            // to a viewer standing in front of the card (+Z, out of the fridge).
            textGO.transform.localRotation = Quaternion.Euler(0f, 180f, 0f);
            // local units == world meters on this object, regardless of the parent's scale
            textGO.transform.localScale = new Vector3(1f / parentScale.x, 1f / parentScale.y, 1f / parentScale.z);

            TextMeshPro tmp = textGO.AddComponent<TextMeshPro>();
            tmp.text = st.text;
            tmp.font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(FontAssetPath);
            tmp.color = Color.black;
            tmp.alignment = TextAlignmentOptions.Center;
            tmp.textWrappingMode = TextWrappingModes.Normal;
            tmp.enableAutoSizing = true;
            tmp.fontSizeMin = 0.5f;
            tmp.fontSizeMax = 14f;

            RectTransform rt = textGO.GetComponent<RectTransform>();
            if (rt != null) rt.sizeDelta = new Vector2(0.27f, 0.19f);

            SceneText sceneText = textGO.AddComponent<SceneText>();
            sceneText.id = st.id;
            sceneText.text = st.text;
        }
    }
}
