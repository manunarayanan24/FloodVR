using UnityEngine;

namespace FloodVR
{
    public class DamageItem : MonoBehaviour
    {
        public string id;
        public string label;
        public string category; // flood | wind | hazard | contents | structural
        public int severity; // 0-5 (0 = confirmed undamaged, e.g. above waterline)
        public float measuredValue;
        public string unit;
        public string note;
        public float heightAboveFloor; // meters; optional, mainly for "contents" items
    }
}
