/* FloodVR voice client (browser / Unity WebGL). Served at GET /voice/client.js.
 *
 * OPEN MIC (default): connect once and just talk. The mic stays on; the agent
 * answers after you pause (~2 s). No button to hold.
 *
 *   await FloodVRVoice.connect("https://<tunnel>")   // call once, ideally from a tap (iOS)
 *   FloodVRVoice.setMuted(true / false)              // optional privacy mute
 *   FloodVRVoice.sendGaze("furnace_flooded")         // what the adjuster is looking at
 *   FloodVRVoice.onReply(r => ...)    // r = /voice response JSON (kind, spoken_reply, updates, ...)
 *   FloodVRVoice.onHeard(t => ...)    // what the agent transcribed (caption)
 *   FloodVRVoice.onStatus(s => ...)   // "connecting" | "waiting for agent" | "ready" | "listening" | "muted" | "error: ..."
 *
 * setMic(on) is kept for old callers but does nothing in open-mic mode, so an
 * old tap-to-talk toggle can't switch the mic off. connect(api, {openMic:false})
 * restores push-to-talk (setMic + floodvr.ptt signals).
 *
 * The agent's spoken reply plays automatically. iOS only allows audio after a
 * tap, so if playback is blocked we unlock it on the next tap anywhere.
 * Replies arrive on data topic floodvr.voice, captions on floodvr.heard.
 */
(function () {
  "use strict";
  var LK_SRC = "https://cdn.jsdelivr.net/npm/livekit-client@2.9.5/dist/livekit-client.umd.min.js";
  var TRAIL_MS = 1200; // push-to-talk only: keep the mic open briefly after release
  var MIC_OPTS = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };

  var room = null, micTimer = null, openMic = true, muted = false, micBlocked = false;
  var cbs = { reply: [], heard: [], status: [] };
  var dec = new TextDecoder(), enc = new TextEncoder();

  function emit(kind, v) { cbs[kind].forEach(function (f) { try { f(v); } catch (e) { console.error(e); } }); }
  function status(s) { emit("status", s); }

  function loadSdk() {
    if (window.LivekitClient) return Promise.resolve(window.LivekitClient);
    return new Promise(function (ok, fail) {
      var s = document.createElement("script");
      s.src = LK_SRC; s.async = true;
      s.onload = function () { ok(window.LivekitClient); };
      s.onerror = function () { fail(new Error("could not load livekit-client")); };
      document.head.appendChild(s);
    });
  }

  function agentPresent() {
    if (!room) return false;
    var found = false;
    room.remoteParticipants.forEach(function (p) { if (String(p.identity).indexOf("agent") === 0) found = true; });
    return found;
  }

  function settle() {
    if (!room) return;
    if (!agentPresent()) { status("waiting for agent"); return; }
    status("ready");
    if (openMic) status(micBlocked ? "error: microphone blocked - allow the mic for this site and reload"
                                   : muted ? "muted" : "listening");
  }

  // iOS/Safari: audio may only start after a user gesture. Retry on any tap.
  function unlockAudio() {
    if (room && !room.canPlaybackAudio) room.startAudio().catch(function () {});
  }
  ["touchend", "pointerdown", "click", "keydown"].forEach(function (ev) {
    document.addEventListener(ev, unlockAudio, true);
  });

  async function connect(apiBase, opts) {
    if (room) return;
    openMic = !(opts && opts.openMic === false);
    var base = String(apiBase).replace(/\/$/, "");
    status("connecting");
    var LK = await loadSdk();
    var res = await fetch(base + "/voice/token", { method: "POST" });
    if (!res.ok) throw new Error("token HTTP " + res.status);
    var tok = await res.json();

    room = new LK.Room({ adaptiveStream: true, dynacast: true, audioCaptureDefaults: MIC_OPTS });
    room.on(LK.RoomEvent.TrackSubscribed, function (track) {
      if (track.kind === "audio") {
        var el = track.attach();
        el.setAttribute("playsinline", "");
        el.style.display = "none";
        document.body.appendChild(el);
      }
    });
    room.on(LK.RoomEvent.TrackUnsubscribed, function (track) { track.detach().forEach(function (el) { el.remove(); }); });
    room.on(LK.RoomEvent.DataReceived, function (payload, participant, kind, topic) {
      var text = dec.decode(payload);
      if (topic === "floodvr.voice") {
        try { emit("reply", JSON.parse(text)); } catch (e) { console.warn("bad reply", e); }
      } else if (topic === "floodvr.heard") {
        emit("heard", text);
      }
    });
    room.on(LK.RoomEvent.ParticipantConnected, function () { settle(); });
    // If the agent drops (e.g. the PC restarted it), ask for it again.
    room.on(LK.RoomEvent.ParticipantDisconnected, function (p) {
      if (String(p.identity).indexOf("agent") === 0 && !agentPresent()) {
        status("waiting for agent");
        nudgeAgent(base, 0);
      }
    });
    room.on(LK.RoomEvent.Disconnected, function () { room = null; status("disconnected"); });

    await room.connect(tok.url, tok.token);
    try { await room.startAudio(); } catch (e) { /* unlocked on the next tap */ }
    if (openMic) {
      try {
        await room.localParticipant.setMicrophoneEnabled(true, MIC_OPTS);
        micBlocked = false;
      } catch (e) {
        micBlocked = true;
      }
    }
    settle();
    if (!agentPresent()) nudgeAgent(base, 0);
  }

  // If the agent has not joined after ~10 s, ask the server to dispatch it again.
  function nudgeAgent(base, tries) {
    setTimeout(function () {
      if (!room || agentPresent() || tries >= 6) return;
      status("waiting for agent (retry " + (tries + 1) + ")");
      fetch(base + "/voice/agent", { method: "POST" }).catch(function () {});
      nudgeAgent(base, tries + 1);
    }, 10000);
  }

  async function setMuted(m) {
    if (!room) return;
    muted = !!m;
    await room.localParticipant.setMicrophoneEnabled(!muted, MIC_OPTS);
    settle();
  }

  // Push-to-talk (only when connected with {openMic:false}). In open-mic mode
  // this is a no-op so an old tap-to-talk toggle can't switch the mic off.
  async function setMic(on) {
    if (!room) throw new Error("connect() first");
    if (openMic) { unlockAudio(); return; }
    clearTimeout(micTimer);
    if (on) {
      ptt("pressed");
      await room.localParticipant.setMicrophoneEnabled(true, MIC_OPTS);
      status("listening");
    } else {
      micTimer = setTimeout(function () {
        ptt("released"); // tells the agent the question is complete
        if (room) room.localParticipant.setMicrophoneEnabled(false);
        settle();
      }, TRAIL_MS);
    }
  }

  function ptt(state) {
    if (!room) return;
    room.localParticipant.publishData(enc.encode(JSON.stringify({ state: state })),
                                      { reliable: true, topic: "floodvr.ptt" });
  }

  function sendGaze(itemId) {
    if (!room) return;
    var body = JSON.stringify({ gaze_item_id: itemId ? String(itemId).slice(0, 80) : null });
    room.localParticipant.publishData(enc.encode(body), { reliable: true, topic: "floodvr.gaze" });
  }

  async function disconnect() { if (room) await room.disconnect(); room = null; }

  window.FloodVRVoice = {
    connect: function (apiBase, opts) {
      return connect(apiBase, opts).catch(function (e) { status("error: " + e.message); room = null; throw e; });
    },
    setMic: setMic, setMuted: setMuted, sendGaze: sendGaze, disconnect: disconnect,
    isConnected: function () { return !!room; },
    isOpenMic: function () { return openMic; },
    onReply: function (f) { cbs.reply.push(f); },
    onHeard: function (f) { cbs.heard.push(f); },
    onStatus: function (f) { cbs.status.push(f); },
  };
})();
