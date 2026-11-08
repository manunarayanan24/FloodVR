using System;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

namespace FloodVR
{
    // Lets the adjuster walk the house: puts a glowing floor marker + floating name at every
    // StandPoint_* in the scene (except the one you are standing on). Look at a marker for ~1.5 s
    // and the rig teleports there. Lives on the VRRig root (added by VRRigBuilder at build time).
    public class StandPointNav : MonoBehaviour
    {
        public const float EyeHeight = 1.6f;
        const string Prefix = "StandPoint_";

        public static event Action<string> OnMoved; // new standpoint name, e.g. "StandPoint_Kitchen"
        public static string CurrentStandPoint { get; private set; } = "";

        class Entry { public Transform stand; public GameObject root; public Transform label; }
        readonly List<Entry> _entries = new List<Entry>();
        Transform _head;
        Transform _current;
        Material _discMat, _beaconMat;
        bool _moving;
        Material _fadeMat;
        GameObject _fade;
        Transform _holder; // markers must NOT be children of the rig, or they'd travel with it

        void Start()
        {
            var look = GetComponentInChildren<HeadLook>(true);
            _head = look != null ? look.transform : transform;

            _holder = new GameObject("StandMarkers").transform;
            // Black quad just in front of the eyes, used to dim the view during a glide (comfort + hides walls).
            _fadeMat = MakeMat(new Color(0f, 0f, 0f, 0f));
            _fade = GameObject.CreatePrimitive(PrimitiveType.Quad);
            _fade.name = "GlideFade";
            Destroy(_fade.GetComponent<Collider>());
            _fade.transform.SetParent(_head, false);
            _fade.transform.localPosition = new Vector3(0f, 0f, 0.25f);
            _fade.transform.localScale = new Vector3(1.6f, 1.6f, 1f);
            var fr = _fade.GetComponent<Renderer>();
            fr.sharedMaterial = _fadeMat;
            fr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            fr.receiveShadows = false;
            _fade.SetActive(false);
            _discMat = MakeMat(new Color(0.25f, 0.75f, 1f, 0.55f));
            _beaconMat = MakeMat(new Color(0.25f, 0.75f, 1f, 0.28f));

            foreach (var t in FindObjectsByType<Transform>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
            {
                if (!t.name.StartsWith(Prefix, StringComparison.Ordinal)) continue;
                if (t.IsChildOf(transform)) continue; // our own markers
                _entries.Add(Build(t));
            }
            _entries.Sort((a, b) => string.CompareOrdinal(a.stand.name, b.stand.name));

            // Start where the rig currently is: the closest standpoint.
            Transform nearest = null; float best = float.MaxValue;
            foreach (var e in _entries)
            {
                float d = Vector3.SqrMagnitude(Flat(e.stand.position) - Flat(transform.position));
                if (d < best) { best = d; nearest = e.stand; }
            }
            SetCurrent(nearest);
        }

        static Vector3 Flat(Vector3 v) { return new Vector3(v.x, 0f, v.z); }

        public static string Pretty(string standName)
        {
            string s = standName.StartsWith(Prefix, StringComparison.Ordinal) ? standName.Substring(Prefix.Length) : standName;
            return s.Replace('_', ' ');
        }

        Entry Build(Transform stand)
        {
            var e = new Entry { stand = stand };
            e.root = new GameObject("Marker_" + stand.name);
            e.root.transform.SetParent(_holder, false);
            float floorY = Mathf.Max(0f, stand.position.y - EyeHeight);
            e.root.transform.position = new Vector3(stand.position.x, floorY, stand.position.z);

            var marker = e.root.AddComponent<StandMarker>();
            marker.stand = stand;
            marker.nav = this;
            marker.displayName = Pretty(stand.name);

            // Floor disc (the gaze target). Wide, short box collider so it is easy to hit.
            var disc = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            disc.name = "Disc";
            disc.transform.SetParent(e.root.transform, false);
            disc.transform.localPosition = new Vector3(0f, 0.015f, 0f);
            disc.transform.localScale = new Vector3(0.8f, 0.01f, 0.8f);
            Destroy(disc.GetComponent<Collider>());
            var box = disc.AddComponent<BoxCollider>();
            box.size = new Vector3(1f, 20f, 1f);
            Style(disc, _discMat);

            // Tall faint beacon so the marker is visible from across the room (no collider).
            var beacon = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            beacon.name = "Beacon";
            beacon.transform.SetParent(e.root.transform, false);
            beacon.transform.localPosition = new Vector3(0f, 0.8f, 0f);
            beacon.transform.localScale = new Vector3(0.08f, 0.8f, 0.08f);
            Destroy(beacon.GetComponent<Collider>());
            var bbox = beacon.AddComponent<BoxCollider>(); // staring at the beam works too
            bbox.size = new Vector3(5f, 2f, 5f);
            Style(beacon, _beaconMat);

            // Floating name.
            var lg = new GameObject("Label");
            lg.transform.SetParent(e.root.transform, false);
            lg.transform.localPosition = new Vector3(0f, 1.75f, 0f);
            var tmp = lg.AddComponent<TextMeshPro>();
            TMP_FontAsset font = TMP_Settings.defaultFontAsset;
            if (font == null) font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            if (font != null) tmp.font = font;
            tmp.richText = false;
            tmp.text = marker.displayName;
            tmp.fontSize = 6f;
            tmp.fontStyle = FontStyles.Bold;
            tmp.alignment = TextAlignmentOptions.Center;
            tmp.textWrappingMode = TextWrappingModes.NoWrap;
            tmp.overflowMode = TextOverflowModes.Overflow;
            tmp.color = new Color(0.55f, 0.9f, 1f);
            tmp.rectTransform.sizeDelta = new Vector2(1.5f, 0.2f);
            e.label = lg.transform;
            return e;
        }

        static void Style(GameObject go, Material m)
        {
            var r = go.GetComponent<Renderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
        }

        // Glides to the StandPoint (about 1-2 s, view dims in the middle so it is comfortable and
        // never shows the camera passing through walls). Keeps the current heading.
        public void GoTo(Transform stand)
        {
            if (stand == null || _moving) return;
            StartCoroutine(Glide(stand));
        }

        IEnumerator Glide(Transform stand)
        {
            _moving = true;
            Vector3 from = transform.position;
            Vector3 p = stand.position;
            Vector3 to = new Vector3(p.x, Mathf.Max(0f, p.y - EyeHeight), p.z);
            float dur = Mathf.Clamp(Vector3.Distance(from, to) / 3.2f, 0.9f, 2.4f);
            foreach (var e in _entries) e.root.SetActive(false); // markers off while moving
            _fade.SetActive(true);
            for (float t = 0f; t < 1f; t += Time.unscaledDeltaTime / dur)
            {
                float s = t * t * (3f - 2f * t); // smoothstep
                transform.position = Vector3.Lerp(from, to, s);
                _fadeMat.color = new Color(0f, 0f, 0f, Mathf.Sin(t * Mathf.PI) * 0.92f);
                yield return null;
            }
            transform.position = to;
            _fade.SetActive(false);
            SetCurrent(stand);
            _moving = false;
            if (OnMoved != null) OnMoved(stand.name);
        }

        void SetCurrent(Transform stand)
        {
            _current = stand;
            CurrentStandPoint = stand != null ? stand.name : "";
            foreach (var e in _entries) e.root.SetActive(e.stand != _current);
        }

        void LateUpdate()
        {
            if (_head == null) return;
            foreach (var e in _entries)
            {
                if (!e.root.activeSelf || e.label == null) continue;
                Vector3 d = e.label.position - _head.position;
                float dist = d.magnitude;
                if (dist < 0.01f) continue;
                e.label.rotation = Quaternion.LookRotation(d, Vector3.up);
                e.label.localScale = Vector3.one * (Mathf.Clamp(dist, 1.5f, 8f) * 0.5f);
            }
        }

        static Material MakeMat(Color c)
        {
            // Overlay shader (Resources/FloodVROverlay) draws through walls so you can see where to go.
            Shader s = Resources.Load<Shader>("FloodVROverlay");
            if (s == null) s = Shader.Find("Sprites/Default");
            if (s == null) s = Shader.Find("UI/Default");
            if (s == null) s = Shader.Find("Standard");
            var m = new Material(s);
            m.color = c;
            return m;
        }
    }
}
