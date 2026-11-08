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

(filled in as the furniture pass adds models)

All downloaded via the public Poly Haven API (`api.polyhaven.com`), diffuse-only / mesh-only
where PBR normal/roughness maps weren't needed for this project's flat-shaded low-poly look.
