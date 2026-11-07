using System.Globalization;
using UnityEngine;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace FloodVR
{
    // Attach to the "Head" transform of the VR rig.
    // WebGL: DeviceOrientation.jslib feeds OnDeviceQuaternion("x,y,z,w").
    // Editor/desktop: mouse-look fallback (hold anywhere / move mouse).
    public class HeadLook : MonoBehaviour
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern void FloodVR_StartOrientation(string goName, string method);
#endif
        [Header("Smoothing")]
        [Tooltip("Higher = snappier. 0 = raw.")]
        public float smoothing = 12f;

        [Header("Axis tuning (flip if head turns the wrong way on device)")]
        public bool invertYaw = false;
        public bool invertPitch = false;

        [Header("Editor mouse-look fallback")]
        public float mouseSensitivity = 3f;

        private Quaternion _target = Quaternion.identity;
        private bool _hasDeviceData = false;
        private float _yaw, _pitch;

        void Start()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            // Sets up the JS listener + window.floodVR.requestPermission (called on tap by the template).
            FloodVR_StartOrientation(gameObject.name, "OnDeviceQuaternion");
#endif
        }

        // Called from DeviceOrientation.jslib.
        public void OnDeviceQuaternion(string csv)
        {
            var p = csv.Split(',');
            if (p.Length != 4) return;
            var ci = CultureInfo.InvariantCulture;
            if (!float.TryParse(p[0], NumberStyles.Float, ci, out float x)) return;
            if (!float.TryParse(p[1], NumberStyles.Float, ci, out float y)) return;
            if (!float.TryParse(p[2], NumberStyles.Float, ci, out float z)) return;
            if (!float.TryParse(p[3], NumberStyles.Float, ci, out float w)) return;

            // Device frame (WebGL, right-handed) -> Unity (left-handed, Y up).
            // Common WebXR/Cardboard conversion; if look feels mirrored/tilted on a
            // real phone, toggle invertYaw/invertPitch rather than editing this.
            _target = new Quaternion(-x, -z, y, w);
            _hasDeviceData = true;
        }

        void Update()
        {
            if (_hasDeviceData)
            {
                Quaternion q = _target;
                if (invertYaw || invertPitch)
                {
                    Vector3 e = q.eulerAngles;
                    if (invertYaw) e.y = -e.y;
                    if (invertPitch) e.x = -e.x;
                    q = Quaternion.Euler(e);
                }
                transform.localRotation = smoothing <= 0f
                    ? q
                    : Quaternion.Slerp(transform.localRotation, q, Time.deltaTime * smoothing);
            }
            else
            {
                _yaw   += Input.GetAxis("Mouse X") * mouseSensitivity;
                _pitch -= Input.GetAxis("Mouse Y") * mouseSensitivity;
                _pitch  = Mathf.Clamp(_pitch, -85f, 85f);
                transform.localRotation = Quaternion.Euler(_pitch, _yaw, 0f);
            }
        }
    }
}
