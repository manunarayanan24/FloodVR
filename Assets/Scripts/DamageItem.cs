using UnityEngine;

namespace FloodVR
{
    public class DamageItem : MonoBehaviour
    {
        public string id;
        public string label;
        public string category; // flood | wind | hazard | contents | structural
        public int severity; // 1-5
        public float measuredValue;
        public string unit;
        public string note;
    }
}
