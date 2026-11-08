using UnityEngine;

namespace FloodVR
{
    // A floor marker the adjuster looks at (dwell) to walk to another StandPoint.
    // Created at runtime by StandPointNav; GazeSelector calls Activate() when the dwell completes.
    public class StandMarker : MonoBehaviour
    {
        public Transform stand;       // the StandPoint_* object to move to
        public StandPointNav nav;
        public string displayName;

        public void Activate()
        {
            if (nav != null && stand != null) nav.GoTo(stand);
        }
    }
}
