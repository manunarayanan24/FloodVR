using System;
using System.Collections;
using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace FloodVR
{
    [Serializable] class VoiceGuard { public bool blocked; }

    [Serializable]
    class VoiceResponse
    {
        public string kind;
        public string spoken_reply;
        public string[] citations;
        public VoiceGuard guard;
    }

    // Tap-to-talk. Tap the screen (or the cardboard button) once to listen, speak, and the
    // transcript goes to POST {api}/voice (contracts/voice.schema.json). The spoken_reply is
    // shown on a head-locked panel and read aloud. The transcript is UNTRUSTED text and is sent
    // as-is for the server's guard to inspect; the reply is shown with rich text OFF.
    // Lives on the VRRig root (its GameObject name is used by the JS bridge).
    public class VoiceClient : MonoBehaviour
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void FloodVR_InitSpeech(string goName);
        [DllImport("__Internal")] static extern void FloodVR_Speak(string text);
#endif
        Transform _head;
        GameObject _hud;
        TextMeshPro _text;
        Transform _bg;
        float _hideAt;

        void Start()
        {
            var look = GetComponentInChildren<HeadLook>(true);
            _head = look != null ? look.transform : transform;
            BuildHud();
#if UNITY_WEBGL && !UNITY_EDITOR
            try { FloodVR_InitSpeech(gameObject.name); } catch (Exception e) { Debug.LogWarning("[FloodVR] speech init: " + e.Message); }
#endif
        }

        // ---- called from JS via SendMessage ----
        public void OnSpeechState(string state)
        {
            if (state == "listening") Show("Listening...  speak now (tap to stop)", 12f);
            else if (state == "unsupported") Show("Voice not supported in this browser", 5f);
            else if (state != null && state.StartsWith("error:", StringComparison.Ordinal))
            {
                string code = state.Substring(6);
                if (code == "not-allowed" || code == "service-not-allowed")
                    Show("Microphone/Speech blocked. iPhone Settings > Siri: turn on Dictation, and allow the mic for this site.", 8f);
                else if (code == "no-speech") Show("Didn't hear anything - tap and try again", 3f);
                else if (code != "aborted") Show("Voice error: " + code, 4f);
            }
            // "idle": keep whatever is on screen
        }

        public void OnSpeechResult(string transcript)
        {
            if (string.IsNullOrEmpty(transcript)) return;
            if (transcript.Length > 1000) transcript = transcript.Substring(0, 1000);
            Show("You: " + transcript + "\n...", 15f);
            ApiConfig.WhenReady(b => StartCoroutine(Send(transcript)));
        }

        IEnumerator Send(string transcript)
        {
            if (string.IsNullOrEmpty(ApiConfig.BaseUrl))
            {
                Show("You: " + transcript + "\n(No AI server set - open the page with ?api=https://...)", 8f);
                yield break;
            }

            var sb = new StringBuilder();
            sb.Append("{\"transcript\":\"").Append(Esc(transcript)).Append('"');
            if (!string.IsNullOrEmpty(StandPointNav.CurrentStandPoint))
                sb.Append(",\"standpoint\":\"").Append(Esc(StandPointNav.CurrentStandPoint)).Append('"');
            if (!string.IsNullOrEmpty(GazeSelector.LastItemId))
                sb.Append(",\"gaze_item_id\":\"").Append(Esc(GazeSelector.LastItemId)).Append('"');
            if (!string.IsNullOrEmpty(CalloutsClient.AuditTrailId))
                sb.Append(",\"audit_trail_id\":\"").Append(Esc(CalloutsClient.AuditTrailId)).Append('"');
            sb.Append('}');

            using (var req = new UnityWebRequest(ApiConfig.Url("/voice"), "POST"))
            {
                req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(sb.ToString()));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                req.timeout = 30;
                yield return req.SendWebRequest();

                if (req.result != UnityWebRequest.Result.Success)
                {
                    Show("You: " + transcript + "\n(AI server not reachable yet: " + req.responseCode + ")", 8f);
                    yield break;
                }
                VoiceResponse r = null;
                try { r = JsonUtility.FromJson<VoiceResponse>(req.downloadHandler.text); } catch (Exception) { }
                if (r == null || string.IsNullOrEmpty(r.spoken_reply))
                {
                    Show("You: " + transcript + "\n(no reply)", 6f);
                    yield break;
                }
                string reply = r.spoken_reply.Length > 300 ? r.spoken_reply.Substring(0, 300) : r.spoken_reply;
                bool blocked = r.guard != null && r.guard.blocked;
                Show((blocked ? "[blocked by guard]  " : "") + reply, 14f);
#if UNITY_WEBGL && !UNITY_EDITOR
                try { FloodVR_Speak(reply); } catch (Exception) { }
#endif
            }
        }

        static string Esc(string s)
        {
            var b = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': b.Append("\\\""); break;
                    case '\\': b.Append("\\\\"); break;
                    case '\n': b.Append("\\n"); break;
                    case '\r': b.Append("\\r"); break;
                    case '\t': b.Append("\\t"); break;
                    default:
                        if (c < 0x20) b.Append("\\u").Append(((int)c).ToString("x4"));
                        else b.Append(c);
                        break;
                }
            }
            return b.ToString();
        }

        // ---- head-locked panel ----
        const float HudW = 0.95f;

        void BuildHud()
        {
            _hud = new GameObject("VoiceHud");
            var bg = GameObject.CreatePrimitive(PrimitiveType.Quad);
            bg.transform.SetParent(_hud.transform, false);
            Destroy(bg.GetComponent<Collider>()); // must never block the gaze ray
            var r = bg.GetComponent<Renderer>();
            r.sharedMaterial = MakeMat(new Color(0.02f, 0.04f, 0.08f, 0.9f));
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.receiveShadows = false;
            _bg = bg.transform;

            var tg = new GameObject("Text");
            tg.transform.SetParent(_hud.transform, false);
            _text = tg.AddComponent<TextMeshPro>();
            TMP_FontAsset font = TMP_Settings.defaultFontAsset;
            if (font == null) font = Resources.Load<TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
            if (font != null) _text.font = font;
            _text.richText = false; // transcript + reply are untrusted
            _text.enableAutoSizing = false;
            _text.fontSize = 1.6f; // ~0.05 m lines at 0.9 m
            _text.color = Color.white;
            _text.alignment = TextAlignmentOptions.Center;
            _text.textWrappingMode = TextWrappingModes.Normal;
            _text.overflowMode = TextOverflowModes.Overflow;
            _hud.SetActive(false);
        }

        void Show(string msg, float seconds)
        {
            if (msg.Length > 420) msg = msg.Substring(0, 420);
            _text.text = msg;
            float tw = HudW - 0.08f;
            _text.rectTransform.sizeDelta = new Vector2(tw, 0.5f);
            float h = Mathf.Clamp(_text.GetPreferredValues(msg, tw, 0f).y, 0.06f, 0.7f) + 0.08f;
            _bg.localScale = new Vector3(HudW, h, 1f);
            _text.rectTransform.sizeDelta = new Vector2(tw, h - 0.08f);
            _text.rectTransform.localPosition = new Vector3(0f, 0f, -0.01f);
            _hud.SetActive(true);
            _hideAt = Time.unscaledTime + seconds;
        }

        void LateUpdate()
        {
            if (_hud == null || !_hud.activeSelf || _head == null) return;
            if (Time.unscaledTime > _hideAt) { _hud.SetActive(false); return; }
            // Head-locked: 0.9 m ahead, a little below the centre so it stays out of the way.
            _hud.transform.position = _head.position + _head.forward * 0.9f - _head.up * 0.3f;
            _hud.transform.rotation = _head.rotation;
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
