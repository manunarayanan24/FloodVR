# FloodVR — Team Coordination README

> **What this is:** the single source of truth for how the three machines on this
> project work together. Read this first, every work session. It replaces re-pasting
> context. If you change how a layer works, update this file in the same commit.

HackUTD 2026 (UTD, Nov 7–8) · State Farm "The Worst Day, at Scale" track (+ NVIDIA Nemotron).
**Goal: win.**

---

## The product in one paragraph

A remote insurance adjuster puts an iPhone into a cardboard VR viewer and walks a 3D
replica of a flooded house. They look around, flag and measure damage, and everything
they find is written to a single structured file, `damage_manifest.json`. AI agents read
that manifest afterward (behind a prompt-injection guard) to draft the claim. No Xcode,
no app store — it ships as a WebGL build opened in iPhone Safari and added to the home
screen, with a QR code for judges.

---

## The three machines

| Machine | Owner | Layer | Owns these paths |
|---|---|---|---|
| **Mac 1** (main planner) | Manu (`manunarayanan24`) | House scene + damage data | `Assets/Scenes/House.unity`, `Assets/Editor/`, `Assets/Data/`, `Assets/Materials/`, `Assets/StreamingAssets/damage_manifest.json`, `Assets/Scripts/DamageItem.cs` |
| **Mac 2** (this machine) | Ayush | Phone-VR layer | `Assets/Scripts/VR/`, `Assets/Plugins/WebGL/`, `Assets/WebGLTemplates/`, `Assets/Scenes/VRTest.unity` |
| **Windows** | Abhinav | AI agent layer | `/agents/` (to be created at repo root — see below) |

**Golden rule to avoid merge conflicts:** only edit files inside *your* paths. Never
hand-edit another machine's files. If you need a change in someone else's layer, ping
them (or note it in a commit touching only your own files).

---

## Fixed technical decisions (do not re-litigate without team agreement)

- **Unity `6000.0.85f2`** — exact version, all machines. Mismatched editors cause reimport
  churn and version ping-pong. (Install "Web Build Support" module; Built-in Render
  Pipeline, **not** URP.)
- **Scene-as-code.** `House.unity` is *generated* by `Assets/Editor/HouseBuilder.cs` from
  `Assets/Data/*.json`. **Never hand-edit `House.unity`** — your changes get wiped on the
  next regenerate.
- Built-in RP, no realtime shadows, textures ≤1024px, low-poly flat colors (keeps the
  WebGL build small and fast on a phone).
- Target: WebGL → iPhone Safari → Add to Home Screen. QR for judges.

---

## The data contract (the interface between all three layers)

This is the one thing every layer depends on. **If you change this schema, update this
section and tell the other two.**

`DamageItem` (component, `Assets/Scripts/DamageItem.cs`) and each entry in
`damage_manifest.json` share these fields:

```jsonc
{
  "id":            "buckled_planks_living_room",  // string, unique
  "label":         "Buckled floor planks",        // string, human-readable
  "category":      "flood",                        // string: flood | wind | hazard | contents | structural
  "severity":      3,                               // int 1-5
  "measuredValue": 2.0,                             // float (the number the adjuster measured)
  "unit":          "cm lift",                       // string (unit for measuredValue)
  "note":          "Living room flooring has buckled...", // string
  "position": { "x": 3.0, "y": 0.03, "z": 5.5 }    // export-only; added from transform at export
}
```

Notes:
- `category` is a **lowercase string**, not an enum. (An earlier draft used a `DamageCategory`
  enum + `adjusterNote` field — that is dead. Use `string category` and `string note`.)
- `position` is **not** a field on the `DamageItem` component; it is written at export time
  from the GameObject's transform. Agents read it from the manifest.
- The manifest is the agent layer's **only** input. Agents must treat `note` and `label`
  as untrusted text and run them behind the prompt-injection guard.

---

## How the VR rig and the house fit together (READ THIS — easy to break)

The VR rig (stereo cameras + head tracking) lives in `Assets/Scripts/VR/` and is added to
a scene by the editor menu **Tools → FloodVR → Add VR Rig to Active Scene**.

**The hazard:** `HouseBuilder.cs` builds `House.unity` with
`EditorSceneManager.NewScene(..., Single)` — it **wipes the whole scene** and rebuilds it.
So if you (a) add the VR rig to `House.unity` and save, then (b) regenerate the house, the
**VR rig is destroyed**.

**The convention (so this never bites us):** the VR rig is added **at build time**, not
saved into `House.unity`. `BuildWeb.cs` (Mac 2) is responsible for ensuring the rig exists
in the scene right before it builds. That means:
- Mac 1 can regenerate `House.unity` freely — it never needs the rig in it.
- Mac 2's **Tools → FloodVR → Build Web** produces a playable build regardless of whether
  the house was just regenerated.
- Do **not** commit a `House.unity` with a VR rig baked in — keep the scene rig-free.

---

## Git workflow

- `git pull --rebase` **before** you start and **before** you push. Always.
- Commit small and often, scoped to your own paths.
- Push to `main` (we're moving fast; no PR ceremony).
- If you hit a conflict, it's almost always because someone edited outside their lane —
  check this README's ownership table.

---

## Build & deploy (Mac 2 owns this)

1. Unity Hub → **Open** → `~/git/FloodVR`
2. **Tools → FloodVR → Build Web** → outputs to `Builds/web/` (gzip + decompression fallback,
   low quality, CardboardVR template).
3. `cd ~/git/FloodVR/Builds/web && vercel deploy` → gives a public URL.
4. `npx qrcode-terminal <url>` → QR for judges.
5. iPhone Safari → URL → **Add to Home Screen** → tap → landscape split-screen with head look.

`Builds/` is gitignored — builds are local, the URL is what we share.

---

## Current status (update as you go)

- **Mac 1 (house):** scene-as-code pipeline in; `House.unity`, materials, `damage.json`,
  `house_layout.json`, and `damage_manifest.json` committed.
- **Mac 2 (phone-VR):** VR rig, head tracking (`HeadLook` + `DeviceOrientation.jslib`),
  CardboardVR WebGL template, `BuildWeb` menu committed. Gaze selection (reticle +
  dwell-to-select + waterline readout) not yet built. Build not yet run (Unity installing).
- **Windows (agents):** Not in repo yet. Target: `/agents/` reading `damage_manifest.json`
  with a prompt-injection guard. Nemotron / Claude for claim drafting.

---

## Open coordination items

1. **VR rig persistence** — adopt the build-time convention above so house regen can't wipe
   the rig. (Mac 2 to harden `BuildWeb.cs` to add the rig if missing.)
2. **Agent layer location** — confirm `/agents/` at repo root (Python) as Abhinav's lane so
   it doesn't collide with the Unity `Assets/` tree.
3. **Manifest refresh** — decide whether the manifest is regenerated by Mac 1's exporter on
   every house change, and whether agents read the committed copy or a runtime export.
