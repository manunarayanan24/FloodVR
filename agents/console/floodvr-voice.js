/* FloodVR voice client (browser / Unity WebGL). Served at GET /voice/client.js.
 *
 *   await FloodVRVoice.connect("https://<tunnel>")   // must run inside a tap (iOS audio + mic)
 *   FloodVRVoice.setMic(true)  ... FloodVRVoice.setMic(false)   // push to talk
 *   FloodVRVoice.sendGaze("furnace_flooded")         // what the adjuster is looking at
 *   FloodVRVoice.onReply(r => ...)    // r = /voice response JSON (kind, spoken_reply, updates, ...)
 *   FloodVRVoice.onHeard(t => ...)    // what the agent transcribed
 *   FloodVRVoice.onStatus(s => ...)   // "connecting" | "waiting for agent" | "ready" | "listening" | "error: ..."
 *
 * The agent's spoken reply plays automatically. Replies arrive on data topic
 * floodvr.voice, transcripts on floodvr.heard. See contracts/voice.schema.json.
 */
(function () {
  "use strict";
  var LK_SRC = "https://cdn.jsdelivr.net/npm/livekit-client@2.9.5/dist/livekit-client.umd.min.js";
  var TRAIL_MS = 1200; // keep the mic open briefly after release so end-of-speech is detected

  var room = null, micTimer = null, cbs = { reply: [], heard: [], status: [] };
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

  async function connect(apiBase) {
    if (room) return;
    status("connecting");
    var LK = await loadSdk();
    var res = await fetch(String(apiBase).replace(/\/$/, "") + "/voice/token", { method: "POST" });
    if (!res.ok) throw new Error("token HTTP " + res.status);
    var tok = await res.json();

    room = new LK.Room({ adaptiveStream: true, dynacast: true });
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
    room.on(LK.RoomEvent.ParticipantConnected, function () { if (agentPresent()) status("ready"); });
    room.on(LK.RoomEvent.Disconnected, function () { room = null; status("disconnected"); });

    await room.connect(tok.url, tok.token);
    await room.startAudio(); // unlocks playback; call connect() from a tap
    status(agentPresent() ? "ready" : "waiting for agent");
    if (!agentPresent()) nudgeAgent(String(apiBase).replace(/\/$/, ""), 0);
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

  async function setMic(on) {
    if (!room) throw new Error("connect() first");
    clearTimeout(micTimer);
    if (on) {
      await room.localParticipant.setMicrophoneEnabled(true);
      status("listening");
    } else {
      micTimer = setTimeout(function () {
        if (room) room.localParticipant.setMicrophoneEnabled(false);
        status(agentPresent() ? "ready" : "waiting for agent");
      }, TRAIL_MS);
    }
  }

  function sendGaze(itemId) {
    if (!room) return;
    var body = JSON.stringify({ gaze_item_id: itemId ? String(itemId).slice(0, 80) : null });
    room.localParticipant.publishData(enc.encode(body), { reliable: true, topic: "floodvr.gaze" });
  }

  async function disconnect() { if (room) await room.disconnect(); room = null; }

  window.FloodVRVoice = {
    connect: function (apiBase) {
      return connect(apiBase).catch(function (e) { status("error: " + e.message); room = null; throw e; });
    },
    setMic: setMic, sendGaze: sendGaze, disconnect: disconnect,
    isConnected: function () { return !!room; },
    onReply: function (f) { cbs.reply.push(f); },
    onHeard: function (f) { cbs.heard.push(f); },
    onStatus: function (f) { cbs.status.push(f); },
  };
})();
