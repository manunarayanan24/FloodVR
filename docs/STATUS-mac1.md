# Mac 1 status

**Done:** House/damage pipeline through iPhone perf pass + first visual pass (prior rounds). This round (40-min time box, second visual pass): fixed a real bug where Poly Haven FBX imports were misread as centimeters (`useFileScale`), shrinking every model 100x -- sofa/bookshelf/chairs now fit correctly off that fix. Coffee table tried twice, reverted both times (model's mesh pivot is off-center, renders wrong) -- documented in CREDITS.md and README 9, left as primitive. No CC0 fridge model exists on Poly Haven (checked), skipped. Kitchen cabinets/counter not attempted this round (time box). Floor/wall textures confirmed showing and tiling correctly. Verified: house_geometry.json byte-identical, 26 DamageItems unchanged, House.unity rig-free, 45,547 tris / 40 batches, Build Web 11.5 MB.

**Doing:** Idle, waiting on requests.

**Blocked:** Nothing.
