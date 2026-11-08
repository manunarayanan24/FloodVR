using UnityEngine;

namespace FloodVR
{
    // Runtime-safe toggle between the pre-flood (clean) and post-flood (damaged)
    // look of the house. Built by DamageBuilder; callable from gameplay code too.
    public static class FloodState
    {
        public static bool IsFlooded { get; private set; } = true;

        // Runtime entry point for a gaze/tap button in the VR headset -- flips
        // between the post-flood (damaged) and pre-flood (clean) view.
        public static void Toggle() => Show(!IsFlooded);

        public static void Show(bool flooded)
        {
            IsFlooded = flooded;

            FloodVisual[] all = Object.FindObjectsByType<FloodVisual>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (FloodVisual fv in all)
            {
                if (fv.additiveOnly)
                {
                    fv.gameObject.SetActive(flooded);
                    continue;
                }

                Renderer rend = fv.GetComponent<Renderer>();
                if (rend != null) rend.sharedMaterial.color = flooded ? fv.damagedColor : fv.cleanColor;

                fv.transform.localScale = flooded ? fv.damagedLocalScale : fv.cleanLocalScale;
                fv.transform.localPosition = flooded ? fv.damagedLocalPosition : fv.cleanLocalPosition;
                fv.transform.localRotation = flooded ? fv.damagedLocalRotation : fv.cleanLocalRotation;
            }

            Debug.Log($"[FloodVR] Flood state set to {(flooded ? "Post-Flood (Damaged)" : "Pre-Flood (Clean)")}, {all.Length} visuals updated.");
        }
    }
}
