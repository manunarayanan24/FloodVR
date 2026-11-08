using System;
using System.Globalization;
using System.Reflection;
using System.Text;
using TMPro;
using UnityEngine;

namespace FloodVR
{
    // Attach to the rig's "Head". Looks along the head's forward vector; when the gaze rests
    // on a DamageItem (or the sticky-note SceneText) for `dwellSeconds`, a world-space label
    // appears next to it. The reticle is a real 3D object at the hit point, so both eyes see
    // it with correct stereo depth.
    //
    // Label text is shown with rich-text parsing OFF: damage notes / scene text are untrusted
    // data and must never be able to inject markup into the UI.
    public class GazeSelector : MonoBehaviour
    {
        [Header("Gaze")]
        public float maxDistance = 6f;
        public float dwellSeconds = 1.5f;
        [Tooltip("How long gaze may stray before the label closes.")]
        public float lostGraceSeconds = 0.35f;

        [Header("Look")]
        public Color idleColor = Color.white;
        public Color dwellColor = new Color(1f, 0.78f, 0.2f);
        public Color selectedColor = new Color(0.35f, 0.9f, 0.5f);

        // Hooks for later (e.g. logging what the adjuster inspected, headset callouts).
        public static string LastItemId = ""; // last damage item the adjuster inspected (sent with voice notes)
        public static event Action<DamageItem> OnItemSelected;
        public static event Action<SceneText> OnSceneTextSelected;

        const int RingSegments = 48;
        const float RingInner = 0.78f;
        const float LabelMetres = 0.86f;  // panel width at scale 1
        const float LabelPad = 0.04f;
        const float TitleH = 0.09f;
        const float BodyGap = 0.02f;
        const float BodySize = 3.2f;     // body font size (world-space TMP units)
        const float BodyMaxH = 0.75f;    // body text taller than this is shrunk to fit
        const float LabelDistance = 0.8f; // label floats this far from the eyes (in front of nearly all geometry)
        Transform _bgT, _barT;

        // Optional field Mac 1 is adding to DamageItem. Read via reflection so this compiles
        // whether or not it exists yet.
        static readonly FieldInfo HeightField =
            typeof(DamageItem).GetField("heightAboveFloor", BindingFlags.Public | BindingFlags.Instance);

        Transform _head;
        GameObject _dot, _ringGo, _panel;
        Material _dotMat, _ringMat;
        Mesh _ringMesh;
        TextMeshPro _title, _body;

        Component _target;
        float _dwell, _lost, _drawnFill = -1f;
        bool _selected;

        void Awake()
        {
            _head = transform;
            BuildVisuals();
        }

        void OnDestroy()
        {
            if (_dot) Destroy(_dot);
            if (_ringGo) Destroy(_ringGo);
            if (_panel) Destroy(_panel);
            if (_ringMesh) Destroy(_ringMesh);
        }

        void LateUpdate() // after HeadLook has rotated the head this frame
        {
            float dt = Time.deltaTime;
            Ray ray = new Ray(_head.position, _head.forward);
            RaycastHit hit;
            bool didHit = Physics.Raycast(ray, out hit, maxDistance, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
            Component key = didHit ? Resolve(hit.collider) : null;
            float dist = didHit ? hit.distance : 2.5f;
            Vector3 point = didHit ? hit.point : ray.origin + ray.direction * dist;

            if (key != null)
            {
                _lost = 0f;
                if (key != _target)
                {
                    _target = key;
                    _dwell = 0f;
                    _selected = false;
                    _panel.SetActive(false);
                }
                if (!_selected)
                {
                    _dwell += dt;
                    if (_dwell >= dwellSeconds)
                    {
                        _dwell = dwellSeconds;
                        _selected = true;
                        Select(key, dist);
                    }
                }
            }
            else if (_target != null)
            {
                _lost += dt;
                if (_lost > lostGraceSeconds)
                {
                    _target = null;
                    _dwell = 0f;
                    _selected = false;
                    _panel.SetActive(false);
                }
            }

            UpdateReticle(point, dist, ray.direction, key != null);

            if (_panel.activeSelf) FacePanel();
        }

        // ---------- targeting ----------

        static Component Resolve(Collider c)
        {
            if (c == null) return null;
            StandMarker sm = c.GetComponentInParent<StandMarker>();
            if (sm != null) return sm;
            CalloutMarker cm = c.GetComponentInParent<CalloutMarker>();
            if (cm != null) return cm;
            Transform t = c.transform;
            // The sticky note is a card + TMP text that are siblings under the fridge. The card
            // would otherwise resolve to the fridge's DamageItem, so check for scene text first.
            if (t.name.StartsWith("SceneText_", StringComparison.Ordinal) && t.parent != null)
            {
                SceneText st = t.parent.GetComponentInChildren<SceneText>(true);
                if (st != null) return st;
            }
            return c.GetComponentInParent<DamageItem>();
        }

        // ---------- reticle ----------

        void UpdateReticle(Vector3 point, float dist, Vector3 dir, bool onTarget)
        {
            float nudge = Mathf.Min(0.03f + dist * 0.01f, dist * 0.5f); // toward the viewer: no z-fighting
            Vector3 pos = point - dir * nudge;

            _dot.transform.position = pos;
            _dot.transform.localScale = Vector3.one * Mathf.Max(0.004f, dist * 0.012f);
            _dotMat.color = !onTarget ? idleColor : (_selected ? selectedColor : dwellColor);

            _ringGo.SetActive(onTarget);
            if (!onTarget) return;

            _ringGo.transform.position = pos;
            _ringGo.transform.rotation = Quaternion.LookRotation(pos - _head.position, _head.up);
            _ringGo.transform.localScale = Vector3.one * (dist * 0.028f);

            float fill = _selected ? 1f : Mathf.Clamp01(_dwell / dwellSeconds);
            if (Mathf.Abs(fill - _drawnFill) > 0.004f)
            {
                BuildRing(fill);
                _drawnFill = fill;
            }
            _ringMat.color = _selected ? selectedColor : dwellColor;
        }

        void BuildRing(float fill)
        {
            int n = Mathf.Max(1, Mathf.CeilToInt(RingSegments * fill));
            float end = Mathf.PI * 2f * fill;
            var verts = new Vector3[(n + 1) * 2];
            var tris = new int[n * 12];
            for (int i = 0; i <= n; i++)
            {
                float a = end * i / n;
                float s = Mathf.Sin(a), c = Mathf.Cos(a);
                verts[i * 2]     = new Vector3(s, c, 0f);                 // outer
                verts[i * 2 + 1] = new Vector3(s * RingInner, c * RingInner, 0f); // inner
            }
            int t = 0;
            for (int i = 0; i < n; i++)
            {
                int o0 = i * 2, i0 = i * 2 + 1, o1 = (i + 1) * 2, i1 = (i + 1) * 2 + 1;
                tris[t++] = o0; tris[t++] = o1; tris[t++] = i0; // front
                tris[t++] = i0; tris[t++] = o1; tris[t++] = i1;
                tris[t++] = o0; tris[t++] = i0; tris[t++] = o1; // back (double-sided)
                tris[t++] = i0; tris[t++] = i1; tris[t++] = o1;
            }
            _ringMesh.Clear();
            _ringMesh.vertices = verts;
            _ringMesh.triangles = tris;
            _ringMesh.RecalculateNormals();
            _ringMesh.RecalculateBounds();
        }

        // ---------- label ----------

        void Select(Component key, float dist)
        {
            string title, body;
            StandMarker sm = key as StandMarker;
            if (sm != null)
            {
                // Walk to that StandPoint, then start fresh (the old target is behind us now).
                sm.Activate();
                _target = null; _dwell = 0f; _selected = false; _lost = 0f;
                _panel.SetActive(false);
                return;
            }
            CalloutMarker cm = key as CalloutMarker;
            DamageItem di = key as DamageItem;
            SceneText st = key as SceneText;
            if (cm != null)
            {
                title = cm.Title;
                body = cm.Body;
            }
            else if (di != null)
            {
                LastItemId = di.id;
                Describe(di, out title, out body);
                if (OnItemSelected != null) OnItemSelected(di);
            }
            else if (st != null)
            {
                string on = st.transform.parent != null ? st.transform.parent.name : "a prop";
                title = "Scene text on " + on;
                body = st.text + "\n\n(Text printed on a prop - not a measured finding)";
                if (OnSceneTextSelected != null) OnSceneTextSelected(st);
            }
            else return;

            _title.text = title;
            _body.text = body;

            // The label floats close to the eyes (so scene geometry such as a tipped fridge door
            // can never poke through it) and is scaled with that distance so it always looks the
            // same size. It sits just above the gaze point.
            float labelDist = Mathf.Clamp(Mathf.Min(dist - 0.1f, LabelDistance), 0.3f, LabelDistance);
            float h = LayoutPanel();
            float up = Mathf.Min(h * 0.5f + 0.06f, 0.55f - h * 0.5f);
            _panel.transform.position = _head.position + _head.forward * labelDist + _head.up * (up * labelDist);
            _panel.transform.localScale = Vector3.one * labelDist;
            FacePanel();
            _panel.SetActive(true);
        }

        // Sizes the panel to fit ALL the text (no clipping), top-aligned, and returns its height.
        float LayoutPanel()
        {
            float tw = LabelMetres - 2f * LabelPad;

            _body.enableAutoSizing = false;
            float size = BodySize;
            float bodyH;
            while (true)
            {
                _body.fontSize = size;
                bodyH = _body.GetPreferredValues(_body.text, tw, 0f).y;
                if (bodyH <= BodyMaxH || size <= 1.4f) break;
                size -= 0.2f;
            }
            bodyH = Mathf.Clamp(bodyH, 0.06f, BodyMaxH + 0.05f);

            float h = LabelPad + TitleH + BodyGap + bodyH + LabelPad;
            float top = h * 0.5f;

            _bgT.localScale = new Vector3(LabelMetres, h, 1f);
            _barT.localPosition = new Vector3(0f, top - 0.006f, -0.002f);

            _title.rectTransform.sizeDelta = new Vector2(tw, TitleH);
            _title.rectTransform.localPosition = new Vector3(0f, top - LabelPad - TitleH * 0.5f, -0.01f);

            _body.rectTransform.sizeDelta = new Vector2(tw, bodyH);
            _body.rectTransform.localPosition = new Vector3(0f, top - LabelPad - TitleH - BodyGap - bodyH * 0.5f, -0.01f);
            return h;
        }

        void FacePanel()
        {
            Vector3 d = _panel.transform.position - _head.position;
            if (d.sqrMagnitude > 1e-4f)
                _panel.transform.rotation = Quaternion.LookRotation(d, _head.up); // text front faces -Z; rolls with the view so it never looks tilted
        }

        static void Describe(DamageItem di, out string title, out string body)
        {
            title = !string.IsNullOrEmpty(di.label) ? di.label : di.id;

            var sb = new StringBuilder();
            string cat = string.IsNullOrEmpty(di.category) ? "uncategorised" : di.category;
            sb.Append(char.ToUpperInvariant(cat[0])).Append(cat.Substring(1)).Append("  |  ");
            if (di.severity <= 0) sb.Append("Undamaged (severity 0)");
            else sb.Append("Severity ").Append(di.severity).Append("/5");
            sb.Append('\n');

            if (IsWaterline(di))
            {
                sb.Append("Water reached ").Append(MetresAndFeet(di.measuredValue)).Append('\n');
            }
            else if (!string.IsNullOrEmpty(di.unit) || Mathf.Abs(di.measuredValue) > 0.0001f)
            {
                sb.Append(di.measuredValue.ToString("0.##", CultureInfo.InvariantCulture));
                if (!string.IsNullOrEmpty(di.unit)) sb.Append(' ').Append(di.unit);
                sb.Append('\n');
            }

            float h;
            if (TryGetHeight(di, out h)) sb.Append("Height above floor: ").Append(MetresAndFeet(h)).Append('\n');

            if (!string.IsNullOrEmpty(di.note)) sb.Append('\n').Append(di.note);
            body = sb.ToString();
        }

        static bool IsWaterline(DamageItem di)
        {
            return di.id != null && di.id.IndexOf("waterline", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        // 0.9 -> "0.90 m (2 ft 11 in)"
        static string MetresAndFeet(float metres)
        {
            int totalIn = Mathf.RoundToInt(metres / 0.0254f);
            int ft = totalIn / 12, inch = totalIn % 12;
            string imperial = ft > 0 ? ft + " ft " + inch + " in" : inch + " in";
            return metres.ToString("0.00", CultureInfo.InvariantCulture) + " m (" + imperial + ")";
        }

        static bool TryGetHeight(DamageItem di, out float h)
        {
            h = 0f;
            if (HeightField == null) return false;
            object v = HeightField.GetValue(di);
            if (v is float f) h = f;
            else if (v is double d) h = (float)d;
            else if (v is int i) h = i;
            else return false;
            return !float.IsNaN(h) && h > 0.001f; // 0 / unset = at floor level, don't print
        }

        // ---------- visuals ----------

        void BuildVisuals()
        {
            _dotMat = MakeMat(idleColor);
            _dot = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            _dot.name = "GazeReticle";
            Prepare(_dot, _dotMat);

            _ringMesh = new Mesh();
            _ringMesh.MarkDynamic();
            _ringMat = MakeMat(dwellColor);
            _ringGo = new GameObject("GazeRing");
            _ringGo.AddComponent<MeshFilter>().sharedMesh = _ringMesh;
            var rr = _ringGo.AddComponent<MeshRenderer>();
            rr.sharedMaterial = _ringMat;
            rr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            rr.receiveShadows = false;
            _ringGo.SetActive(false);

            _panel = new GameObject("GazePanel");
            var bg = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bg.name = "Bg";
            bg.transform.SetParent(_panel.transform, false);
            bg.transform.localScale = new Vector3(LabelMetres, 0.44f, 1f);
            Prepare(bg, MakeMat(new Color(0.04f, 0.06f, 0.10f, 1f)));
            _bgT = bg.transform;

            var bar = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bar.name = "Accent";
            bar.transform.SetParent(_panel.transform, false);
            bar.transform.localPosition = new Vector3(0f, 0.214f, -0.002f);
            bar.transform.localScale = new Vector3(LabelMetres, 0.012f, 1f);
            Prepare(bar, MakeMat(dwellColor));
            _barT = bar.transform;

            _title = MakeText("Title", new Vector3(0f, 0.15f, -0.01f), new Vector2(0.64f, 0.08f),
                               6f, FontStyles.Bold, dwellColor, TextAlignmentOptions.Left);
            _body = MakeText("Body", new Vector3(0f, -0.04f, -0.01f), new Vector2(0.64f, 0.28f),
                              3f, FontStyles.Normal, Color.white, TextAlignmentOptions.TopLeft);
            _panel.SetActive(false);
        }

        TextMeshPro MakeText(string name, Vector3 localPos, Vector2 size, float maxSize,
                             FontStyles style, Color color, TextAlignmentOptions align)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_panel.transform, false);
            go.transform.localPosition = localPos;
            var t = go.AddComponent<TextMeshPro>();

            TMP_FontAsset font = TMP_Settings.defaultFontAsset;
            if (font == null) font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            if (font != null) t.font = font;

            t.rectTransform.sizeDelta = size;
            t.richText = false; // untrusted text: no markup
            t.enableAutoSizing = true;
            t.fontSizeMin = 0.1f;
            t.fontSizeMax = maxSize;
            t.fontStyle = style;
            t.color = color;
            t.alignment = align;
            t.textWrappingMode = TextWrappingModes.Normal;
            t.overflowMode = TextOverflowModes.Overflow; // panel is sized to fit the text, so never clip
            return t;
        }

        static void Prepare(GameObject go, Material mat)
        {
            var col = go.GetComponent<Collider>();
            if (col != null) Destroy(col); // must never block the gaze ray
            var r = go.GetComponent<Renderer>();
            r.sharedMaterial = mat;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
        }

        // Sprites/Default is in Always Included Shaders (checked in GraphicsSettings.asset), so it
        // survives into the WebGL build. Fall back to Standard (used by Mac 1's materials).
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
