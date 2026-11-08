// FloodVR LiveKit voice for Unity WebGL (Mac 2 lane: copy to Assets/Scripts/VR/LiveKitVoice.cs,
// and FloodVRVoice.jslib to Assets/Plugins/WebGL/). Put it on the VRRig root next to VoiceClient.
//
// Flow: first tap -> Connect() (joins LiveKit room "floodvr"; the NVIDIA voice agent on the
// Windows PC joins too). Hold/tap -> SetMic(true), release -> SetMic(false). The agent hears
// the question (Parakeet), answers from claim data and SPEAKS the reply itself (Magpie), so do
// NOT also call FloodVR_Speak for LiveKit replies. Text arrives in OnVoiceReply for the HUD.
// Replies are untrusted-safe server templates, but show them with rich text OFF anyway.
using System;
using UnityEngine;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace FloodVR
{
    [Serializable] class LkGuard { public bool blocked; }
    [Serializable] class LkReply { public string kind; public string spoken_reply; public LkGuard guard; }

    public class LiveKitVoice : MonoBehaviour
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void FloodVRVoice_Connect(string apiBase, string goName);
        [DllImport("__Internal")] static extern void FloodVRVoice_SetMic(int on);
        [DllImport("__Internal")] static extern void FloodVRVoice_SendGaze(string itemId);
        [DllImport("__Internal")] static extern void FloodVRVoice_Disconnect();
#endif
        public static string Status { get; private set; } = "off";
        public static bool Ready => Status == "ready" || Status == "listening";

        public static event Action<string> StatusChanged;          // "connecting", "ready", "listening", "error: ..."
        public static event Action<string> Heard;                  // what the agent transcribed
        public static event Action<string, bool> Replied;          // (spoken_reply, blockedByGuard)

        string _lastGaze;

        // Call from a tap. Safe to call again; it only connects once.
        public void Connect()
        {
            if (Status != "off" && !Status.StartsWith("error", StringComparison.Ordinal)) return;
            ApiConfig.WhenReady(baseUrl =>
            {
                if (string.IsNullOrEmpty(baseUrl)) { OnVoiceStatus("error: no API url"); return; }
#if UNITY_WEBGL && !UNITY_EDITOR
                FloodVRVoice_Connect(baseUrl, gameObject.name);
#else
                OnVoiceStatus("error: LiveKit voice needs the WebGL build");
#endif
            });
        }

        public void SetMic(bool on)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            if (Ready) FloodVRVoice_SetMic(on ? 1 : 0);
#endif
        }

        void Update()
        {
            // Tell the agent what the adjuster is looking at, so "is this covered?" resolves.
            string g = GazeSelector.LastItemId;
            if (Ready && g != _lastGaze)
            {
                _lastGaze = g;
#if UNITY_WEBGL && !UNITY_EDITOR
                FloodVRVoice_SendGaze(g ?? "");
#endif
            }
        }

        void OnDestroy()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            if (Status != "off") FloodVRVoice_Disconnect();
#endif
        }

        // ---- called from JS via SendMessage ----
        public void OnVoiceStatus(string s) { Status = s ?? "off"; StatusChanged?.Invoke(Status); }

        public void OnVoiceHeard(string t) { if (!string.IsNullOrEmpty(t)) Heard?.Invoke(t.Length > 500 ? t.Substring(0, 500) : t); }

        public void OnVoiceReply(string json)
        {
            LkReply r = null;
            try { r = JsonUtility.FromJson<LkReply>(json); } catch (Exception) { }
            if (r == null || string.IsNullOrEmpty(r.spoken_reply)) return;
            string reply = r.spoken_reply.Length > 300 ? r.spoken_reply.Substring(0, 300) : r.spoken_reply;
            Replied?.Invoke(reply, r.guard != null && r.guard.blocked);
        }
    }
}
