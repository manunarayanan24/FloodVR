// FloodVR voice bridge for Unity WebGL.
// Copy to Assets/Plugins/WebGL/FloodVRVoice.jslib (Mac 2 lane).
// It loads <apiBase>/voice/client.js from the Windows server, which does the
// LiveKit work, then forwards replies to a GameObject via SendMessage.
mergeInto(LibraryManager.library, {

  // Call from a tap (iOS needs a user gesture for mic + audio).
  // gameObject receives: OnVoiceStatus(string), OnVoiceHeard(string), OnVoiceReply(string json)
  FloodVRVoice_Connect: function (apiBasePtr, gameObjectPtr) {
    var apiBase = UTF8ToString(apiBasePtr).replace(/\/$/, "");
    var go = UTF8ToString(gameObjectPtr);
    function start() {
      var V = window.FloodVRVoice;
      if (!window.__floodvrVoiceWired) {
        window.__floodvrVoiceWired = true;
        V.onStatus(function (s) { SendMessage(go, "OnVoiceStatus", s); });
        V.onHeard(function (t) { SendMessage(go, "OnVoiceHeard", t); });
        V.onReply(function (r) { SendMessage(go, "OnVoiceReply", JSON.stringify(r)); });
      }
      V.connect(apiBase).catch(function (e) { SendMessage(go, "OnVoiceStatus", "error: " + e.message); });
    }
    if (window.FloodVRVoice) { start(); return; }
    var s = document.createElement("script");
    s.src = apiBase + "/voice/client.js";
    s.onload = start;
    s.onerror = function () { SendMessage(go, "OnVoiceStatus", "error: could not load voice client"); };
    document.head.appendChild(s);
  },

  FloodVRVoice_SetMic: function (on) {
    if (window.FloodVRVoice && window.FloodVRVoice.isConnected()) window.FloodVRVoice.setMic(!!on);
  },

  FloodVRVoice_SendGaze: function (itemIdPtr) {
    if (window.FloodVRVoice) window.FloodVRVoice.sendGaze(UTF8ToString(itemIdPtr));
  },

  FloodVRVoice_Disconnect: function () {
    if (window.FloodVRVoice) window.FloodVRVoice.disconnect();
  }
});
