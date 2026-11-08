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
