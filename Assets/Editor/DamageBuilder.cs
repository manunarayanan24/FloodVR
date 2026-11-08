using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace FloodVR
{
    [Serializable]
    public class DamageEffect
    {
        public string type;
        public string targetId;
        public string room;
        public float heightM;
        public float darkenFactor;
        public float thicknessCm;
        public float scaleMultiplier;
        public float angleDeg;
        public string axis;
        public int count;
        public Vec3Data pos;
        public Vec3Data size;
        public float rotationY;
        public ColorData color;
    }

    [Serializable]
    public class DamageItemData
    {
        public string id, label, category, unit, note;
        public int severity;
        public float measuredValue;
        public float heightAboveFloor;
        public DamageEffect effect;
    }

    [Serializable]
    public class DamageManifestInput
    {
        public DamageItemData[] items;
    }

    [Serializable]
    public class DamageManifestEntry
    {
        public string id, label, category, unit, note;
        public int severity;
        public float measuredValue;
        public float heightAboveFloor;
        public Vec3Data position;
    }

    [Serializable]
    public class SceneTextEntry
    {
        public string id;
        public string text;
    }

    [Serializable]
    public class DamageManifestOutput
    {
        public DamageManifestEntry[] items;
        public SceneTextEntry[] scene_text;
    }

    // Furniture/outlet ids that get independently mutated at runtime by
    // FloodState -- transform = position/rotation/scale changes (unsafe for
    // static batching, since static meshes bake world-space once); color =
    // color-only changes (static-batching-safe, but needs a dedicated
    // material so the mutation doesn't bleed into other objects sharing it).
    public class MutatingTargets
    {
        public HashSet<string> transform = new();
        public HashSet<string> color = new();
    }

    public static class DamageBuilder
    {
        public const string DamageJsonPath = "Assets/Data/damage.json";
        public const string ManifestOutputPath = "Assets/StreamingAssets/damage_manifest.json";

        public static DamageManifestInput LoadDamage()
        {
            string path = Path.Combine(Application.dataPath, "Data/damage.json");
            if (!File.Exists(path))
            {
                Debug.LogError($"[FloodVR] damage.json not found at {path}");
                return null;
            }
            return JsonUtility.FromJson<DamageManifestInput>(File.ReadAllText(path));
        }

        public static MutatingTargets GetMutatingTargetIds()
        {
            MutatingTargets result = new MutatingTargets();
            DamageManifestInput damage = LoadDamage();
            if (damage?.items == null) return result;

            foreach (DamageItemData item in damage.items)
            {
                if (item.effect == null || string.IsNullOrEmpty(item.effect.targetId)) continue;
                switch (item.effect.type)
                {
                    case "tipFurniture":
                        result.transform.Add(item.effect.targetId);
                        break;
                    case "scaleFurniture":
                        result.transform.Add(item.effect.targetId);
                        result.color.Add(item.effect.targetId);
                        break;
                    case "darkenFurniture":
                    case "flagExisting":
                        result.color.Add(item.effect.targetId);
                        break;
                }
            }
            return result;
        }

        public static void ApplyDamage(Transform houseRoot, HouseLayout layout)
        {
            DamageManifestInput damage = LoadDamage();
            if (damage == null || damage.items == null) return;

            GameObject damageRoot = new GameObject("Damage");
            damageRoot.transform.SetParent(houseRoot, false);

            foreach (DamageItemData item in damage.items)
            {
                GameObject carrier = ApplyEffect(houseRoot, damageRoot.transform, layout, item);
                if (carrier == null) continue;

                bool mutating = item.effect.type == "scaleFurniture" || item.effect.type == "tipFurniture"
                    || item.effect.type == "darkenFurniture" || item.effect.type == "flagExisting";
                bool untouched = item.effect.type == "tagOnly"; // existing furniture, no visual change in either flood state
                if (!mutating && !untouched && carrier.GetComponent<FloodVisual>() == null)
                {
                    FloodVisual fv = carrier.AddComponent<FloodVisual>();
                    fv.additiveOnly = true;
                }

                DamageItem di = carrier.GetComponent<DamageItem>();
                if (di == null) di = carrier.AddComponent<DamageItem>();
                di.id = item.id;
                di.label = item.label;
                di.category = item.category;
                di.severity = item.severity;
                di.measuredValue = item.measuredValue;
                di.unit = item.unit;
                di.note = item.note;
                di.heightAboveFloor = item.heightAboveFloor;
            }
        }

        private static GameObject ApplyEffect(Transform houseRoot, Transform damageRoot, HouseLayout layout, DamageItemData item)
        {
            DamageEffect fx = item.effect;
            if (fx == null) return null;

            switch (fx.type)
            {
                case "waterline":
                    return BuildWaterlineOverlays(damageRoot, layout, item, fx);

                case "floorMud":
                    return BuildFloorMud(damageRoot, layout, item, fx);

                case "buckledPlanks":
                    return BuildBuckledPlanks(damageRoot, layout, item, fx);

                case "baseboard":
                    return BuildBaseboard(damageRoot, layout, item, fx);

                case "scaleFurniture":
                    return ApplyScaleFurniture(item, fx);

                case "tipFurniture":
                    return ApplyTipFurniture(item, fx);

                case "darkenFurniture":
                    return ApplyDarkenFurniture(item, fx);

                case "ceilingStain":
                    return BuildCeilingStain(damageRoot, layout, item, fx);

                case "flagExisting":
                    return ApplyFlagExisting(item, fx);

                case "tagOnly":
                    return ApplyTagOnly(item, fx);

                case "decal":
                    return BuildDecal(damageRoot, item, fx);

                default:
                    Debug.LogWarning($"[FloodVR] Unknown damage effect type '{fx.type}' for item '{item.id}'");
                    return null;
            }
        }

        private static RoomData FindRoom(HouseLayout layout, string roomId)
        {
            return layout.rooms?.FirstOrDefault(r => r.id == roomId);
        }

        // Purely additive: lays a slightly-oversized dark overlay panel over the
        // bottom of every wall span that touches the ground, so it can be
        // toggled off entirely for the pre-flood view without needing to
        // un-resize the original wall geometry.
        private static GameObject BuildWaterlineOverlays(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            GameObject group = new GameObject($"Damage_{item.id}");
            group.transform.SetParent(damageRoot, false);

            Color darkColor = layout.house.wallColor.ToColor() * fx.darkenFactor;
            Material mat = HouseBuilder.GetOrCreateMaterial(darkColor, "WallWet");

            float waterlineHeight = fx.heightM;
            float wallHeight = layout.house.wallHeight;
            float thickness = layout.house.wallThickness * 1.02f;
            int segIndex = 0;

            foreach (WallData wall in layout.walls)
            {
                Vector3 p1 = new Vector3(wall.x1, 0f, wall.z1);
                Vector3 p2 = new Vector3(wall.x2, 0f, wall.z2);
                Vector3 delta = p2 - p1;
                float totalLength = delta.magnitude;
                if (totalLength < 0.001f) continue;
                Vector3 dir = delta.normalized;
                float angle = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;

                List<OpeningData> openings = (wall.openings ?? new OpeningData[0]).OrderBy(o => o.start).ToList();
                float cursor = 0f;
                foreach (OpeningData o in openings)
                {
                    if (o.start > cursor + 0.0001f)
                        EmitWaterlineOverlaySegment(group.transform, p1, dir, angle, cursor, o.start, 0f, Mathf.Min(waterlineHeight, wallHeight), thickness, mat, ref segIndex);

                    if (o.bottom > 0.0001f)
                        EmitWaterlineOverlaySegment(group.transform, p1, dir, angle, o.start, o.end, 0f, Mathf.Min(waterlineHeight, o.bottom), thickness, mat, ref segIndex);

                    cursor = o.end;
                }

                if (cursor < totalLength - 0.0001f)
                    EmitWaterlineOverlaySegment(group.transform, p1, dir, angle, cursor, totalLength, 0f, Mathf.Min(waterlineHeight, wallHeight), thickness, mat, ref segIndex);
            }

            return group;
        }

        private static void EmitWaterlineOverlaySegment(Transform parent, Vector3 p1, Vector3 dir, float angle,
            float segStart, float segEnd, float bottom, float top, float thickness, Material mat, ref int segIndex)
        {
            float length = segEnd - segStart;
            if (length <= 0.0001f || top - bottom <= 0.0001f) return;

            float centerDist = (segStart + segEnd) / 2f;
            Vector3 pos = p1 + dir * centerDist;
            pos.y = (bottom + top) / 2f;

            GameObject seg = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"waterline_{segIndex++}", parent);
            seg.transform.position = pos;
            seg.transform.rotation = Quaternion.Euler(0f, angle, 0f);
            seg.transform.localScale = new Vector3(thickness, top - bottom, length);
            seg.GetComponent<Renderer>().sharedMaterial = mat;
            HouseBuilder.MarkBatchingStatic(seg);
        }

        private static GameObject BuildFloorMud(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            float thicknessM = fx.thicknessCm / 100f;
            float wt = layout.house.wallThickness;
            GameObject mud = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"Damage_{item.id}", damageRoot);
            mud.transform.position = new Vector3(layout.house.width / 2f, thicknessM / 2f + 0.002f, layout.house.depth / 2f);
            mud.transform.localScale = new Vector3(layout.house.width - wt * 2f, thicknessM, layout.house.depth - wt * 2f);
            mud.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor());
            HouseBuilder.MarkBatchingStatic(mud);
            return mud;
        }

        private static GameObject BuildBuckledPlanks(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            RoomData room = FindRoom(layout, fx.room);
            if (room == null) return null;

            GameObject group = new GameObject($"Damage_{item.id}");
            group.transform.SetParent(damageRoot, false);

            Material mat = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor());
            float cx = (room.minX + room.maxX) / 2f;
            float cz = (room.minZ + room.maxZ) / 2f;
            group.transform.position = new Vector3(cx, 0.03f, cz);
            int count = Mathf.Max(1, fx.count);

            for (int i = 0; i < count; i++)
            {
                GameObject plank = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"plank_{i}", group.transform);
                float offsetX = (i - (count - 1) / 2f) * 0.5f;
                plank.transform.position = new Vector3(cx + offsetX, 0.03f, cz);
                plank.transform.rotation = Quaternion.Euler(0f, (i % 2 == 0) ? 3f : -4f, 0f);
                plank.transform.localScale = new Vector3(1.2f, 0.04f, 0.25f);
                plank.GetComponent<Renderer>().sharedMaterial = mat;
                HouseBuilder.MarkBatchingStatic(plank);
            }

            return group;
        }

        private static GameObject BuildBaseboard(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            RoomData room = FindRoom(layout, fx.room);
            if (room == null) return null;

            GameObject group = new GameObject($"Damage_{item.id}");
            group.transform.SetParent(damageRoot, false);
            Material mat = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor());

            float width = room.maxX - room.minX;
            float depth = room.maxZ - room.minZ;
            float cx = (room.minX + room.maxX) / 2f;
            float cz = (room.minZ + room.maxZ) / 2f;
            group.transform.position = new Vector3(cx, 0.05f, cz);

            AddStrip(group.transform, mat, new Vector3(cx, 0.05f, room.minZ + 0.02f), new Vector3(width, 0.1f, 0.03f));
            AddStrip(group.transform, mat, new Vector3(cx, 0.05f, room.maxZ - 0.02f), new Vector3(width, 0.1f, 0.03f));
            AddStrip(group.transform, mat, new Vector3(room.minX + 0.02f, 0.05f, cz), new Vector3(0.03f, 0.1f, depth));
            AddStrip(group.transform, mat, new Vector3(room.maxX - 0.02f, 0.05f, cz), new Vector3(0.03f, 0.1f, depth));

            return group;
        }

        private static void AddStrip(Transform parent, Material mat, Vector3 pos, Vector3 scale)
        {
            GameObject strip = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, "baseboard_strip", parent);
            strip.transform.position = pos;
            strip.transform.localScale = scale;
            strip.GetComponent<Renderer>().sharedMaterial = mat;
            HouseBuilder.MarkBatchingStatic(strip);
        }

        private static GameObject ApplyScaleFurniture(DamageItemData item, DamageEffect fx)
        {
            GameObject go = GameObject.Find(fx.targetId);
            if (go == null)
            {
                Debug.LogWarning($"[FloodVR] scaleFurniture target '{fx.targetId}' not found for '{item.id}'");
                return null;
            }

            Renderer rend = go.GetComponent<Renderer>();
            Vector3 cleanScale = go.transform.localScale;
            Vector3 damagedScale = cleanScale * fx.scaleMultiplier;
            Color cleanColor = rend != null ? rend.sharedMaterial.color : Color.white;
            Color damagedColor = cleanColor * fx.darkenFactor;

            FloodVisual fv = go.AddComponent<FloodVisual>();
            fv.additiveOnly = false;
            fv.cleanLocalScale = cleanScale;
            fv.damagedLocalScale = damagedScale;
            fv.cleanColor = cleanColor;
            fv.damagedColor = damagedColor;
            fv.cleanLocalPosition = fv.damagedLocalPosition = go.transform.localPosition;
            fv.cleanLocalRotation = fv.damagedLocalRotation = go.transform.localRotation;

            go.transform.localScale = damagedScale;
            if (rend != null)
            {
                rend.sharedMaterial.color = damagedColor;
                EditorUtility.SetDirty(rend.sharedMaterial);
            }
            return go;
        }

        private static GameObject ApplyTipFurniture(DamageItemData item, DamageEffect fx)
        {
            GameObject go = GameObject.Find(fx.targetId);
            if (go == null)
            {
                Debug.LogWarning($"[FloodVR] tipFurniture target '{fx.targetId}' not found for '{item.id}'");
                return null;
            }

            Vector3 size = go.transform.localScale;
            float rad = fx.angleDeg * Mathf.Deg2Rad;
            float newHalfHeight;
            Vector3 axisVec;
            switch (fx.axis)
            {
                case "x":
                    axisVec = Vector3.right;
                    newHalfHeight = (size.y * Mathf.Abs(Mathf.Cos(rad)) + size.z * Mathf.Abs(Mathf.Sin(rad))) / 2f;
                    break;
                case "y":
                    axisVec = Vector3.up;
                    newHalfHeight = size.y / 2f;
                    break;
                default:
                    axisVec = Vector3.forward;
                    newHalfHeight = (size.y * Mathf.Abs(Mathf.Cos(rad)) + size.x * Mathf.Abs(Mathf.Sin(rad))) / 2f;
                    break;
            }

            Quaternion cleanRotation = go.transform.localRotation;
            Vector3 cleanPosition = go.transform.localPosition;

            Quaternion damagedRotation = Quaternion.AngleAxis(fx.angleDeg, axisVec) * cleanRotation;
            Vector3 damagedPosition = cleanPosition;
            damagedPosition.y = newHalfHeight;

            FloodVisual fv = go.AddComponent<FloodVisual>();
            fv.additiveOnly = false;
            fv.cleanLocalRotation = cleanRotation;
            fv.damagedLocalRotation = damagedRotation;
            fv.cleanLocalPosition = cleanPosition;
            fv.damagedLocalPosition = damagedPosition;
            fv.cleanLocalScale = fv.damagedLocalScale = go.transform.localScale;
            Renderer rend = go.GetComponent<Renderer>();
            fv.cleanColor = fv.damagedColor = rend != null ? rend.sharedMaterial.color : Color.white;

            go.transform.localRotation = damagedRotation;
            go.transform.localPosition = damagedPosition;
            return go;
        }

        private static GameObject ApplyDarkenFurniture(DamageItemData item, DamageEffect fx)
        {
            GameObject go = GameObject.Find(fx.targetId);
            if (go == null)
            {
                Debug.LogWarning($"[FloodVR] darkenFurniture target '{fx.targetId}' not found for '{item.id}'");
                return null;
            }
            Renderer rend = go.GetComponent<Renderer>();
            Color cleanColor = rend != null ? rend.sharedMaterial.color : Color.white;
            Color damagedColor = cleanColor * fx.darkenFactor;
            AttachUnchangedTransformFloodVisual(go, cleanColor, damagedColor);

            if (rend != null)
            {
                rend.sharedMaterial.color = damagedColor;
                EditorUtility.SetDirty(rend.sharedMaterial);
            }
            return go;
        }

        private static GameObject ApplyFlagExisting(DamageItemData item, DamageEffect fx)
        {
            GameObject go = GameObject.Find(fx.targetId);
            if (go == null)
            {
                Debug.LogWarning($"[FloodVR] flagExisting target '{fx.targetId}' not found for '{item.id}'");
                return null;
            }
            Renderer rend = go.GetComponent<Renderer>();
            Color cleanColor = rend != null ? rend.sharedMaterial.color : Color.white;
            Color damagedColor = fx.color.ToColor();
            AttachUnchangedTransformFloodVisual(go, cleanColor, damagedColor);

            if (rend != null)
            {
                rend.sharedMaterial.color = damagedColor;
                EditorUtility.SetDirty(rend.sharedMaterial);
            }
            return go;
        }

        // Tags an existing object as ground truth without changing its look at
        // all -- for content items that are confirmed undamaged in both the
        // pre- and post-flood views (e.g. above the waterline).
        private static GameObject ApplyTagOnly(DamageItemData item, DamageEffect fx)
        {
            GameObject go = GameObject.Find(fx.targetId);
            if (go == null)
            {
                Debug.LogWarning($"[FloodVR] tagOnly target '{fx.targetId}' not found for '{item.id}'");
                return null;
            }
            return go;
        }

        private static void AttachUnchangedTransformFloodVisual(GameObject go, Color cleanColor, Color damagedColor)
        {
            FloodVisual fv = go.AddComponent<FloodVisual>();
            fv.additiveOnly = false;
            fv.cleanColor = cleanColor;
            fv.damagedColor = damagedColor;
            fv.cleanLocalScale = fv.damagedLocalScale = go.transform.localScale;
            fv.cleanLocalPosition = fv.damagedLocalPosition = go.transform.localPosition;
            fv.cleanLocalRotation = fv.damagedLocalRotation = go.transform.localRotation;
        }

        private static GameObject BuildCeilingStain(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            RoomData room = FindRoom(layout, fx.room);
            if (room == null) return null;

            float cx = (room.minX + room.maxX) / 2f;
            float cz = (room.minZ + room.maxZ) / 2f;
            float width = room.maxX - room.minX;
            float depth = room.maxZ - room.minZ;

            GameObject stain = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"Damage_{item.id}", damageRoot);
            stain.transform.position = new Vector3(cx, layout.house.wallHeight - 0.12f, cz);
            stain.transform.localScale = new Vector3(width * 0.5f, 0.05f, depth * 0.4f);
            stain.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor());
            HouseBuilder.MarkBatchingStatic(stain);
            return stain;
        }

        private static GameObject BuildDecal(Transform damageRoot, DamageItemData item, DamageEffect fx)
        {
            GameObject decal = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"Damage_{item.id}", damageRoot);
            decal.transform.position = fx.pos.ToVector3();
            decal.transform.rotation = Quaternion.Euler(0f, fx.rotationY, 0f);
            decal.transform.localScale = fx.size.ToVector3();
            decal.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor());
            HouseBuilder.MarkBatchingStatic(decal);
            return decal;
        }

        // Opens Assets/Scenes/House.unity if it isn't already the active scene.
        // Returns false (and logs) if the scene doesn't exist yet.
        internal static bool EnsureHouseSceneOpen()
        {
            if (GameObject.Find(HouseBuilder.HouseRootName) != null) return true;

            string fullScenePath = Path.Combine(Application.dataPath, "../" + HouseBuilder.ScenePath);
            if (!File.Exists(fullScenePath))
            {
                Debug.LogError("[FloodVR] House.unity not found. Run Tools > FloodVR > Build House first.");
                return false;
            }

            EditorSceneManager.OpenScene(HouseBuilder.ScenePath);
            return true;
        }

        [MenuItem("Tools/FloodVR/Show Pre-Flood (Clean)")]
        public static void ShowPreFlood()
        {
            if (EnsureHouseSceneOpen()) FloodState.Show(false);
        }

        [MenuItem("Tools/FloodVR/Show Post-Flood (Damaged)")]
        public static void ShowPostFlood()
        {
            if (EnsureHouseSceneOpen()) FloodState.Show(true);
        }

        [MenuItem("Tools/FloodVR/Export Damage Manifest")]
        public static void ExportDamageManifest()
        {
            if (!EnsureHouseSceneOpen()) return;

            DamageItem[] allItems = UnityEngine.Object.FindObjectsByType<DamageItem>(FindObjectsSortMode.None);
            if (allItems.Length == 0)
            {
                Debug.LogWarning("[FloodVR] No DamageItem components found in the open scene. Run Tools > FloodVR > Build House first.");
                return;
            }

            DamageManifestEntry[] entries = allItems.Select(di => new DamageManifestEntry
            {
                id = di.id,
                label = di.label,
                category = di.category,
                severity = di.severity,
                measuredValue = di.measuredValue,
                unit = di.unit,
                note = di.note,
                heightAboveFloor = di.heightAboveFloor,
                position = new Vec3Data { x = di.transform.position.x, y = di.transform.position.y, z = di.transform.position.z }
            }).OrderBy(e => e.id).ToArray();

            SceneText[] allSceneTexts = UnityEngine.Object.FindObjectsByType<SceneText>(FindObjectsSortMode.None);
            SceneTextEntry[] sceneTextEntries = allSceneTexts
                .Select(st => new SceneTextEntry { id = st.id, text = st.text })
                .OrderBy(e => e.id)
                .ToArray();

            DamageManifestOutput output = new DamageManifestOutput { items = entries, scene_text = sceneTextEntries };
            string json = JsonUtility.ToJson(output, true);

            HouseBuilder.EnsureFolder("Assets/StreamingAssets");
            string fullPath = Path.Combine(Application.dataPath, "StreamingAssets/damage_manifest.json");
            File.WriteAllText(fullPath, json);
            AssetDatabase.Refresh();

            Debug.Log($"[FloodVR] Exported {entries.Length} damage items and {sceneTextEntries.Length} scene_text entries to {ManifestOutputPath}");
        }
    }
}
