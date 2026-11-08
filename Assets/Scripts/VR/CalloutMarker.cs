using UnityEngine;

namespace FloodVR
{
    // One headset callout (from GET /callouts) placed in the house. Gaze at it to expand the
    // longer `detail` text in the normal gaze panel. Text is untrusted: GazeSelector shows it
    // with rich text OFF.
    public class CalloutMarker : MonoBehaviour
    {
        public string Title = "";
        public string Body = "";
        public string ItemId = "";
    }
}
