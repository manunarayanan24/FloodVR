# Third-party assets

All assets below are CC0 (public domain) and stored under `Assets/ThirdParty/<source>/`.
Textures capped at 1024px, max texture size enforced in the Unity importer.

## Poly Haven (https://polyhaven.com) — CC0

### Textures (`Assets/ThirdParty/PolyHaven/Textures/`)
| File | Poly Haven asset | Used for |
|---|---|---|
| `wood_floor_diff_1k.jpg` | [wood_floor](https://polyhaven.com/a/wood_floor) | Living room / hallway / closet floor |
| `floor_tiles_02_diff_1k.jpg` | [floor_tiles_02](https://polyhaven.com/a/floor_tiles_02) | Kitchen floor |
| `painted_plaster_wall_diff_1k.jpg` | [painted_plaster_wall](https://polyhaven.com/a/painted_plaster_wall) | Interior walls |

Diffuse-only (no normal/roughness maps) -- this project is flat-shaded low-poly with no
realtime shadows, so PBR maps wouldn't be visible anyway. 1024x1024, max texture size and
mipmaps enforced via `HouseBuilder.LoadConstrainedTexture`.

### Models (`Assets/ThirdParty/PolyHaven/Models/`)
| File | Poly Haven asset | Used for |
|---|---|---|
| `Sofa_01.fbx` | [Sofa_01](https://polyhaven.com/a/Sofa_01) | Living room sofa |
| `Shelf_01.fbx` | [Shelf_01](https://polyhaven.com/a/Shelf_01) | Living room bookshelf |
| `WoodenChair_01.fbx` | [WoodenChair_01](https://polyhaven.com/a/WoodenChair_01) | Kitchen chairs (both) |

Mesh-only FBX (no texture maps imported) -- each model's renderer is assigned the original
primitive's own flat-color material, so DamageState color mutations (darkening, hazard
flagging) still work and the model stays visually consistent with the scene's flat-shaded
look. Technique: `FurnitureModelBuilder.cs` disables the original primitive's MeshRenderer
(keeping its GameObject/id/position/collider/DamageItem untouched) and adds the model as a
child, scaled to the primitive's original footprint.

`CoffeeTable_01` was tried and reverted TWICE, across two visual passes:
1. First pass: the fit scaling looked visibly wrong (narrow/tall).
2. Second pass: found and fixed the real root cause for *all* models -- Unity's FBX importer
   had `useFileScale` on and misread these Poly Haven exports as centimeters (`fileScale: 0.01`),
   shrinking every mesh 100x before any fitting math ran. Fixed in `LoadModelWithCorrectScale()`.
   Sofa/bookshelf/chairs now fit correctly off this fix, but `CoffeeTable_01` specifically
   *still* renders wrong -- its mesh content is off-center from its own pivot, which
   `FitModelToPrimitive` doesn't correct for. Reverted again rather than debug per-model pivot
   offsets within the time box; left as the primitive. Worth adding a pivot-recentering step
   (shift the instance so its bounds *center*, not just its bottom, matches the target) in a
   future pass.

No CC0 fridge/refrigerator model exists in Poly Haven's catalog (checked by category and
keyword search) -- the fridge is still the original primitive. Kitchen cabinets/counter were
not attempted in the second pass (ran out of time box); `drawer_cabinet` and
`modern_wooden_cabinet` were scouted as candidates but not downloaded into the final commit.

All downloaded via the public Poly Haven API (`api.polyhaven.com`), diffuse-only / mesh-only
where PBR normal/roughness maps weren't needed for this project's flat-shaded low-poly look.
