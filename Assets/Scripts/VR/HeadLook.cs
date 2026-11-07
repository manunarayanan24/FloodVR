using System.Globalization;
using UnityEngine;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace FloodVR
{
    // Attach to the "Head" transform of the VR rig.
    // WebGL: DeviceOrientation.jslib feeds OnDeviceQuaternion("x,y,z,w") with the camera
    // orientation (three.js convention: right-handed, Y up, looks down -Z, already corrected
    // for the phone being held in landscape). We convert it to Unity's left-handed frame.
    // Editor/desktop: mouse-look fallback.
    //
    // Yaw is relative: the first time the phone is held level (or on Recenter()), the current
    // heading becomes "straight ahead" = the rig's forward (the StandPoint's look direction).
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

        [Header("Recentre")]
        [Tooltip("Auto-recentre once the phone has been held level this long (it went into the viewer).")]
        public float autoRecenterLevelSeconds = 0.75f;
        public float levelPitchLimit = 30f;

        [Header("Editor mouse-look fallback")]
        public float mouseSensitivity = 3f;

        private Quaternion _sensor = Quaternion.identity; // Unity-frame camera orientation from the phone
        private bool _hasDeviceData = false;
        private float _yawOffset = 0f;
        private bool _recentered = false;
        private float _levelTime = 0f;
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

            // three.js (right-handed, camera looks -Z) -> Unity (left-handed, camera looks +Z):
            // mirror the Z axis, which negates the x and y quaternion components.
            _sensor = new Quaternion(-x, -y, z, w);
            _hasDeviceData = true;
        }

        // Makes the current heading "straight ahead". Callable from JS: window.floodVR.recenter().
        public void Recenter()
        {
            if (_hasDeviceData) _yawOffset = -YawOf(_sensor);
            _yaw = 0f;
            _recentered = true;
        }

        static float YawOf(Quaternion q)
        {
            Vector3 f = q * Vector3.forward;
            return Mathf.Atan2(f.x, f.z) * Mathf.Rad2Deg;
        }

        static float Wrap(float a)
        {
            a %= 360f;
            if (a > 180f) a -= 360f;
            if (a < -180f) a += 360f;
            return a;
        }

        void Update()
        {
            if (_hasDeviceData)
            {
                if (!_recentered)
                {
                    Vector3 f = _sensor * Vector3.forward;
                    float pitch = Mathf.Asin(Mathf.Clamp(f.y, -1f, 1f)) * Mathf.Rad2Deg;
                    if (Mathf.Abs(pitch) < levelPitchLimit)
                    {
                        _levelTime += Time.unscaledDeltaTime;
                        if (_levelTime >= autoRecenterLevelSeconds) Recenter();
                    }
                    else _levelTime = 0f;
                }

                Quaternion q = Quaternion.Euler(0f, _yawOffset, 0f) * _sensor;
                if (invertYaw || invertPitch)
                {
                    Vector3 e = q.eulerAngles;
                    float ex = Wrap(e.x), ey = Wrap(e.y), ez = Wrap(e.z);
                    if (invertYaw) ey = -ey;
                    if (invertPitch) ex = -ex;
                    q = Quaternion.Euler(ex, ey, ez);
                }
                transform.localRotation = smoothing <= 0f
                    ? q
                    : Quaternion.Slerp(transform.localRotation, q, Mathf.Clamp01(Time.deltaTime * smoothing));
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
