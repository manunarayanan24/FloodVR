using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace FloodVR
{
    [Serializable]
    class ApiConfigFile
    {
        public string apiBaseUrl;
    }

    // Finds the AI agents' base URL at runtime, so a new Windows tunnel URL never needs a rebuild.
    // Order of precedence:
    //   1. ?api=https://xxxx in the page URL (also remembered in localStorage by the jslib)
    //   2. StreamingAssets/config.json  ->  { "apiBaseUrl": "https://xxxx" }
    //      (editable in Builds/web/StreamingAssets/ after a build; just redeploy)
    // Creates itself automatically after the first scene loads.
    //
    // Usage:  ApiConfig.WhenReady(baseUrl => StartCoroutine(Get(ApiConfig.Url("/callouts"))));
    public class ApiConfig : MonoBehaviour
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern string FloodVR_GetQueryParam(string name);
#endif
        public static string BaseUrl { get; private set; } = "";   // no trailing slash; "" = not configured
        public static string Source { get; private set; } = "none"; // "query" | "config.json" | "none"
        public static bool Ready { get; private set; }
        public static event Action<string> OnReady;

        static ApiConfig _instance;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Bootstrap()
        {
            if (_instance != null) return;
            var go = new GameObject("FloodVR_ApiConfig");
            DontDestroyOnLoad(go);
            _instance = go.AddComponent<ApiConfig>();
        }

        // Runs `cb(baseUrl)` now if already resolved, otherwise as soon as it is. baseUrl may be "".
        public static void WhenReady(Action<string> cb)
        {
            if (cb == null) return;
            if (Ready) cb(BaseUrl);
            else OnReady += cb;
        }

        // ApiConfig.Url("/callouts") -> "https://xxxx/callouts"
        public static string Url(string path)
        {
            if (string.IsNullOrEmpty(path)) return BaseUrl;
            return BaseUrl + (path[0] == '/' ? path : "/" + path);
        }

        IEnumerator Start()
        {
            string fromQuery = ReadQueryParam("api");
            if (!string.IsNullOrEmpty(fromQuery))
            {
                Apply(fromQuery, "query");
                yield break;
            }

            string text = null;
            string path = Path.Combine(Application.streamingAssetsPath, "config.json");
            if (path.Contains("://"))
            {
                // WebGL / Android: StreamingAssets is served over HTTP. Cache-bust so an edited
                // config.json is picked up immediately.
                using (var req = UnityWebRequest.Get(path + "?t=" + DateTime.UtcNow.Ticks))
                {
                    yield return req.SendWebRequest();
                    if (req.result == UnityWebRequest.Result.Success) text = req.downloadHandler.text;
                    else Debug.LogWarning("[FloodVR] config.json not loaded: " + req.error);
                }
            }
            else if (File.Exists(path))
            {
                text = File.ReadAllText(path);
            }

            string fromFile = null;
            if (!string.IsNullOrEmpty(text))
            {
                try { fromFile = JsonUtility.FromJson<ApiConfigFile>(text).apiBaseUrl; }
                catch (Exception e) { Debug.LogWarning("[FloodVR] config.json is not valid JSON: " + e.Message); }
            }
            Apply(fromFile, "config.json");
        }

        static string ReadQueryParam(string name)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            try { return FloodVR_GetQueryParam(name); } catch (Exception) { return ""; }
#else
            return "";
#endif
        }

        static void Apply(string url, string source)
        {
            url = (url ?? "").Trim().TrimEnd('/');
            if (url.Length > 0 && !url.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                               && !url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                Debug.LogWarning("[FloodVR] Ignoring API url without http(s)://: " + url);
                url = "";
            }
            if (url.StartsWith("http://", StringComparison.OrdinalIgnoreCase))
                Debug.LogWarning("[FloodVR] API url is plain http: an https page (Vercel) cannot call it on iPhone. Use an https tunnel.");

            BaseUrl = url;
            Source = url.Length > 0 ? source : "none";
            Ready = true;
            Debug.Log("[FloodVR] API base url: " + (url.Length > 0 ? url : "(not configured)") + "  [" + Source + "]");

            var handlers = OnReady;
            OnReady = null;
            if (handlers != null) handlers(BaseUrl);
        }
    }
}
