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

`CoffeeTable_01` was tried and reverted within this time-boxed pass: its footprint-fit scale
produced a visibly wrong (narrow/tall) orientation. Left as the original primitive rather
than ship something broken-looking -- worth a closer look (correct pivot/axis handling per
model) in a future pass.

All downloaded via the public Poly Haven API (`api.polyhaven.com`), diffuse-only / mesh-only
where PBR normal/roughness maps weren't needed for this project's flat-shaded low-poly look.
