using UnityEngine;

namespace FloodVR
{
    // Marks a piece of readable in-scene text that is NOT a damage finding --
    // e.g. a note prop. Exported separately from DamageItem in the manifest
    // so downstream AI agents don't mistake it for ground-truth damage.
    public class SceneText : MonoBehaviour
    {
        public string id;
        public string text;
    }
}
