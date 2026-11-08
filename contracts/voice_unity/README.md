# OPEN MIC (current, 2026-11-08) — what Mac 2 must do

Push-to-talk is gone. `/voice/client.js` (served by the Windows server, no rebuild needed for it) now
turns the mic on at connect and keeps it on; the agent answers ~2 s after the adjuster stops talking,
and ignores its own voice coming back through the speaker. `setMic()` is now a no-op, so the existing
tap toggle in `DeviceOrientation.jslib` is harmless.

**Blocking bug in the current app:** nothing calls `LiveKitVoice.Connect()`, so LiveKit never starts
in the VR app (taps fall back to Safari speech). Fix, then rebuild + redeploy:

1. `Assets/Scripts/VR/VoiceClient.cs`, end of `Start()`:
   ```csharp
   if (_lk != null) ApiConfig.WhenReady(b => _lk.Connect());
   ```
   (Connecting from the "Enter VR" tap is even better for iOS; if audio is blocked at first, the client
   unlocks it on the next tap anywhere.)
2. Same file, `OnLiveKitStatus`: change the "ready" text to `"Voice ready - just talk"` and show
   `"Microphone blocked - allow the mic and reload"` when the status starts with `error: microphone`.
3. Rebuild, redeploy, test on the iPhone: enter VR, allow the mic, say "How high did the water get?",
   pause. Captions (`OnVoiceHeard` / `OnVoiceReply`) appear on the HUD; the agent speaks the answer.

Optional: `window.FloodVRVoice.setMuted(true/false)` for a privacy mute.

---

# LiveKit voice for the headset (for Ayushmaan / Mac 2)

The Windows side is live: LiveKit Cloud project, NVIDIA voice agent `floodvr-voice`
(Parakeet speech-to-text, Magpie text-to-speech), and the claim brain behind `/voice`.
Tested end to end with spoken audio on 2026-11-07.

Your current tap-to-talk (Safari speech recognition → `POST /voice` → `speechSynthesis`)
keeps working. LiveKit is the upgrade: NVIDIA speech in and out, the agent speaks the answer.

## 1. Try it on the iPhone first (no Unity needed)

Open `https://<tunnel>/voice-test` in Safari (tunnel URL is at the top of
`docs/STATUS-windows.md`). Tap **Connect**, allow the mic, wait for `ready`, then
**hold to talk**: "What are the safety hazards in this house?" You should see what the
agent heard, see the reply, and hear it.

## 2. Add it to the VR app (3 files, ~10 lines of glue)

1. Copy `FloodVRVoice.jslib` → `Assets/Plugins/WebGL/FloodVRVoice.jslib`.
2. Copy `LiveKitVoice.cs` → `Assets/Scripts/VR/LiveKitVoice.cs`, and add the component to
   the VRRig root (same GameObject as `VoiceClient`).
3. In `VoiceClient`, on the tap:

```csharp
var lk = GetComponent<LiveKitVoice>();
if (lk != null && LiveKitVoice.Ready) {            // LiveKit path
    lk.SetMic(true);  /* on release (or next tap): */  lk.SetMic(false);
} else {
    if (lk != null) lk.Connect();                   // first tap connects (needs the gesture)
    // ...existing Safari speech path as fallback...
}
```

and subscribe once in `Start()` to show text on your HUD (the agent already speaks, so
don't call `FloodVR_Speak` for these):

```csharp
LiveKitVoice.Heard   += t => Show("You: " + t + "\n...", 15f);
LiveKitVoice.Replied += (reply, blocked) => Show((blocked ? "[blocked by guard]  " : "") + reply, 14f);
LiveKitVoice.StatusChanged += s => { if (s.StartsWith("error")) Show("Voice: " + s, 5f); };
```

Gaze is sent automatically from `GazeSelector.LastItemId`, so "is this covered?" works.

## How it fits together

- `FloodVRVoice.jslib` loads `<api>/voice/client.js` from the Windows server. That script
  holds all the LiveKit logic, so fixes there need no Unity rebuild.
- `POST /voice/token` → `{url, token, room: "floodvr", identity, agent}`. The token makes
  LiveKit dispatch the agent when the room is created; if the room already exists the
  server re-dispatches (`agent` field says which happened).
- Data topics: `floodvr.voice` (reply JSON, see `contracts/voice.schema.json`),
  `floodvr.heard` (transcript, sanitised), `floodvr.gaze` (you → agent).
- Voice can only propose notes; nothing changes coverage, peril or cost.

## Needs to be running on the Windows PC

Server + tunnel + `python -m agents.voice.worker dev`. If the agent never says "ready",
the worker is not running.
