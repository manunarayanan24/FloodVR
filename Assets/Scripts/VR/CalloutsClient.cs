using System;
using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;

namespace FloodVR
{
    [Serializable] class CalloutPos { public float x; public float y; public float z; }

    [Serializable]
    class CalloutDto
    {
        public string id;
        public string item_id;
        public string kind;
        public string text;
        public int priority;
        public CalloutPos position;
        public string room;
        public string color;
        public string detail;
    }

    [Serializable]
    class CalloutsResponse
    {
        public string generated_at;
        public string audit_trail_id;
        public float waterline_m;
        public CalloutDto[] callouts;
    }

    // Fetches GET {api}/callouts (contracts/callouts.schema.json) and shows each callout as a
    // coloured dot + one line of text in the house. Until Windows' /callouts is live this just
    // retries quietly. Lives on the VRRig root.
    public class CalloutsClient : MonoBehaviour
    {
        public static string AuditTrailId = "";

        const float RetrySeconds = 15f;
        const float RefreshSeconds = 45f;
        const int MaxCallouts = 40;

        readonly List<GameObject> _spawned = new List<GameObject>();
        readonly List<Transform> _labels = new List<Transform>();
        Transform _head;
        string _lastRaw = "";
        TMP_FontAsset _font;
        Material _dotMat;

        void Start()
        {
            var look = GetComponentInChildren<HeadLook>(true);
            _head = look != null ? look.transform : transform;
            _font = TMP_Settings.defaultFontAsset;
            if (_font == null) _font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            ApiConfig.WhenReady(_ => StartCoroutine(Poll()));
        }

        IEnumerator Poll()
        {
            if (string.IsNullOrEmpty(ApiConfig.BaseUrl)) yield break; // no API configured (add ?api=...)
            while (true)
            {
                bool ok = false;
                using (var req = UnityWebRequest.Get(ApiConfig.Url("/callouts")))
                {
                    req.timeout = 10;
                    yield return req.SendWebRequest();
                    if (req.result == UnityWebRequest.Result.Success)
                    {
                        string raw = req.downloadHandler.text;
                        if (raw != _lastRaw)
                        {
                            _lastRaw = raw;
                            ok = Apply(raw);
                        }
                        else ok = true;
                    }
                }
                yield return new WaitForSeconds(ok ? RefreshSeconds : RetrySeconds);
            }
        }

        bool Apply(string raw)
        {
            CalloutsResponse r;
            try { r = JsonUtility.FromJson<CalloutsResponse>(raw); }
            catch (Exception e) { Debug.LogWarning("[FloodVR] /callouts parse failed: " + e.Message); return false; }
            if (r == null || r.callouts == null) return false;

            AuditTrailId = r.audit_trail_id ?? "";
            Clear();
            int n = 0;
            foreach (var c in r.callouts)
            {
                if (c == null || n >= MaxCallouts) continue;
                Vector3 pos;
                if (!TryAnchor(c, out pos)) continue;
                Spawn(c, pos);
                n++;
            }
            Debug.Log("[FloodVR] callouts shown: " + n + " (audit " + AuditTrailId + ")");
            return true;
        }

        static bool TryAnchor(CalloutDto c, out Vector3 pos)
        {
            pos = Vector3.zero;
            if (c.position != null && (c.position.x != 0f || c.position.y != 0f || c.position.z != 0f))
            {
                pos = new Vector3(c.position.x, c.position.y, c.position.z);
                return true;
            }
            if (string.IsNullOrEmpty(c.item_id)) return false;
            // No point given: sit above the damage item (or scene-text prop) it refers to.
            foreach (var di in FindObjectsByType<DamageItem>(FindObjectsSortMode.None))
                if (di.id == c.item_id) return Above(di.transform, out pos);
            foreach (var st in FindObjectsByType<SceneText>(FindObjectsSortMode.None))
                if (st.id == c.item_id) return Above(st.transform.parent != null ? st.transform.parent : st.transform, out pos);
            return false;
        }

        static bool Above(Transform t, out Vector3 pos)
        {
            var r = t.GetComponentInChildren<Renderer>();
            pos = r != null ? r.bounds.center + Vector3.up * (r.bounds.extents.y + 0.3f) : t.position + Vector3.up * 1.2f;
            return true;
        }

        void Spawn(CalloutDto c, Vector3 pos)
        {
            string text = Clip(c.text, 90);
            string detail = Clip(c.detail, 300);
            string kind = string.IsNullOrEmpty(c.kind) ? "note" : Clip(c.kind, 20);
            Color col = ColorFor(c.color);

            var go = new GameObject("Callout_" + (c.id ?? "x"));
            go.transform.position = pos;
            var marker = go.AddComponent<CalloutMarker>();
            marker.Title = kind.ToUpperInvariant() + "  (priority " + Mathf.Clamp(c.priority, 1, 5) + ")";
            marker.Body = string.IsNullOrEmpty(detail) ? text : text + "\n\n" + detail;
            marker.ItemId = c.item_id ?? "";

            var dot = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            dot.transform.SetParent(go.transform, false);
            dot.transform.localScale = Vector3.one * (c.priority <= 1 ? 0.22f : 0.16f);
            var sc = dot.GetComponent<SphereCollider>();
            if (sc != null) sc.radius = 1.6f; // generous gaze target
            var rend = dot.GetComponent<Renderer>();
            rend.sharedMaterial = MakeMat(col);
            rend.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            rend.receiveShadows = false;

            var lg = new GameObject("Text");
            lg.transform.SetParent(go.transform, false);
            lg.transform.localPosition = new Vector3(0f, 0.28f, 0f);
            var tmp = lg.AddComponent<TextMeshPro>();
            if (_font != null) tmp.font = _font;
            tmp.richText = false; // text is untrusted
            tmp.text = text;
            tmp.fontSize = c.priority <= 2 ? 4.5f : 3.5f;
            tmp.fontStyle = FontStyles.Bold;
            tmp.alignment = TextAlignmentOptions.Bottom;
            tmp.textWrappingMode = TextWrappingModes.Normal;
            tmp.overflowMode = TextOverflowModes.Overflow;
            tmp.color = col;
            tmp.rectTransform.sizeDelta = new Vector2(1.5f, 0.5f);
            _labels.Add(lg.transform);
            _spawned.Add(go);
        }

        void Clear()
        {
            foreach (var g in _spawned) if (g != null) Destroy(g);
            _spawned.Clear();
            _labels.Clear();
        }

        void LateUpdate()
        {
            if (_head == null) return;
            for (int i = 0; i < _labels.Count; i++)
            {
                var t = _labels[i];
                if (t == null) continue;
                Vector3 d = t.position - _head.position;
                float dist = d.magnitude;
                if (dist < 0.01f) continue;
                t.rotation = Quaternion.LookRotation(d, Vector3.up);
                t.localScale = Vector3.one * (Mathf.Clamp(dist, 1.2f, 7f) * 0.4f);
            }
        }

        static string Clip(string s, int max)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Length <= max ? s : s.Substring(0, max);
        }

        static Color ColorFor(string name)
        {
            switch (name)
            {
                case "red":   return new Color(1f, 0.28f, 0.22f);
                case "amber": return new Color(1f, 0.72f, 0.12f);
                case "green": return new Color(0.3f, 0.9f, 0.4f);
                default:      return new Color(0.35f, 0.72f, 1f); // blue / unknown
            }
        }

        static Material MakeMat(Color c)
        {
            Shader s = Shader.Find("Sprites/Default");
            if (s == null) s = Shader.Find("UI/Default");
            if (s == null) s = Shader.Find("Standard");
            var m = new Material(s);
            m.color = c;
            return m;
        }
    }
}
