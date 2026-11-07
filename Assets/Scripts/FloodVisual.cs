using UnityEngine;

namespace FloodVR
{
    // Carries the clean ("pre-flood") and damaged ("post-flood") state for one
    // piece of the scene so FloodState.Show(bool) can swap between them.
    public class FloodVisual : MonoBehaviour
    {
        public bool additiveOnly; // pure overlay geometry (mud/decals/etc.) -- just toggled active/inactive

        public Color cleanColor = Color.white;
        public Color damagedColor = Color.white;

        public Vector3 cleanLocalScale;
        public Vector3 damagedLocalScale;

        public Vector3 cleanLocalPosition;
        public Vector3 damagedLocalPosition;

        public Quaternion cleanLocalRotation = Quaternion.identity;
        public Quaternion damagedLocalRotation = Quaternion.identity;
    }
}
