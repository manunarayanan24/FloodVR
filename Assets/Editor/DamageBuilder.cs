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
        public Vec3Data position;
    }

    [Serializable]
    public class DamageManifestOutput
    {
        public DamageManifestEntry[] items;
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

                DamageItem di = carrier.GetComponent<DamageItem>();
                if (di == null) di = carrier.AddComponent<DamageItem>();
                di.id = item.id;
                di.label = item.label;
                di.category = item.category;
                di.severity = item.severity;
                di.measuredValue = item.measuredValue;
                di.unit = item.unit;
                di.note = item.note;
            }
        }

        private static GameObject ApplyEffect(Transform houseRoot, Transform damageRoot, HouseLayout layout, DamageItemData item)
        {
            DamageEffect fx = item.effect;
            if (fx == null) return null;

            switch (fx.type)
            {
                case "waterline":
                    SplitWallsAtWaterline(houseRoot, fx.heightM, fx.darkenFactor);
                    GameObject waterlineMarker = new GameObject($"Damage_{item.id}");
                    waterlineMarker.transform.SetParent(damageRoot, false);
                    waterlineMarker.transform.position = new Vector3(layout.house.width / 2f, fx.heightM, layout.house.depth / 2f);
                    return waterlineMarker;

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

        private static void SplitWallsAtWaterline(Transform houseRoot, float waterlineHeight, float darkenFactor)
        {
            Transform wallsRoot = houseRoot.Find("Walls");
            if (wallsRoot == null) return;

            Material wetMat = HouseBuilder.GetOrCreateMaterial(
                HouseBuilder.materialCache.TryGetValue("Wall", out Material dry) ? dry.color * darkenFactor : Color.gray * darkenFactor,
                "WallWet");

            List<Transform> segments = new();
            CollectCubeSegments(wallsRoot, segments);

            foreach (Transform seg in segments)
            {
                float height = seg.localScale.y;
                float bottom = seg.position.y - height / 2f;
                float top = seg.position.y + height / 2f;
                if (bottom > 0.01f || top <= waterlineHeight + 0.001f) continue;

                float upperHeight = top - waterlineHeight;
                float lowerHeight = waterlineHeight - bottom;

                seg.localScale = new Vector3(seg.localScale.x, upperHeight, seg.localScale.z);
                seg.position = new Vector3(seg.position.x, waterlineHeight + upperHeight / 2f, seg.position.z);

                GameObject wetSeg = GameObject.Instantiate(seg.gameObject, seg.parent);
                wetSeg.name = seg.name + "_wet";
                wetSeg.transform.localScale = new Vector3(seg.localScale.x, lowerHeight, seg.localScale.z);
                wetSeg.transform.position = new Vector3(seg.position.x, bottom + lowerHeight / 2f, seg.position.z);
                wetSeg.transform.rotation = seg.rotation;
                wetSeg.GetComponent<Renderer>().sharedMaterial = wetMat;
            }
        }

        private static void CollectCubeSegments(Transform root, List<Transform> result)
        {
            foreach (Transform child in root)
            {
                if (child.GetComponent<MeshFilter>() != null) result.Add(child);
                CollectCubeSegments(child, result);
            }
        }

        private static GameObject BuildFloorMud(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            float thicknessM = fx.thicknessCm / 100f;
            float wt = layout.house.wallThickness;
            GameObject mud = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"Damage_{item.id}", damageRoot);
            mud.transform.position = new Vector3(layout.house.width / 2f, thicknessM / 2f + 0.002f, layout.house.depth / 2f);
            mud.transform.localScale = new Vector3(layout.house.width - wt * 2f, thicknessM, layout.house.depth - wt * 2f);
            mud.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor(), item.id);
            return mud;
        }

        private static GameObject BuildBuckledPlanks(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            RoomData room = FindRoom(layout, fx.room);
            if (room == null) return null;

            GameObject group = new GameObject($"Damage_{item.id}");
            group.transform.SetParent(damageRoot, false);

            Material mat = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor(), item.id);
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
            }

            return group;
        }

        private static GameObject BuildBaseboard(Transform damageRoot, HouseLayout layout, DamageItemData item, DamageEffect fx)
        {
            RoomData room = FindRoom(layout, fx.room);
            if (room == null) return null;

            GameObject group = new GameObject($"Damage_{item.id}");
            group.transform.SetParent(damageRoot, false);
            Material mat = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor(), item.id);

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
        }

        private static GameObject ApplyScaleFurniture(DamageItemData item, DamageEffect fx)
        {
            GameObject go = GameObject.Find(fx.targetId);
            if (go == null)
            {
                Debug.LogWarning($"[FloodVR] scaleFurniture target '{fx.targetId}' not found for '{item.id}'");
                return null;
            }
            go.transform.localScale *= fx.scaleMultiplier;
            Renderer rend = go.GetComponent<Renderer>();
            if (rend != null)
            {
                rend.sharedMaterial.color *= fx.darkenFactor;
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

            go.transform.rotation = Quaternion.AngleAxis(fx.angleDeg, axisVec) * go.transform.rotation;
            Vector3 pos = go.transform.position;
            pos.y = newHalfHeight;
            go.transform.position = pos;
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
            if (rend != null)
            {
                rend.sharedMaterial.color *= fx.darkenFactor;
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
            if (rend != null)
            {
                rend.sharedMaterial.color = fx.color.ToColor();
                EditorUtility.SetDirty(rend.sharedMaterial);
            }
            return go;
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
            stain.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor(), item.id);
            return stain;
        }

        private static GameObject BuildDecal(Transform damageRoot, DamageItemData item, DamageEffect fx)
        {
            GameObject decal = HouseBuilder.CreatePrimitiveChild(PrimitiveType.Cube, $"Damage_{item.id}", damageRoot);
            decal.transform.position = fx.pos.ToVector3();
            decal.transform.rotation = Quaternion.Euler(0f, fx.rotationY, 0f);
            decal.transform.localScale = fx.size.ToVector3();
            decal.GetComponent<Renderer>().sharedMaterial = HouseBuilder.GetOrCreateMaterial(fx.color.ToColor(), item.id);
            return decal;
        }

        [MenuItem("Tools/FloodVR/Export Damage Manifest")]
        public static void ExportDamageManifest()
        {
            if (GameObject.Find(HouseBuilder.HouseRootName) == null)
            {
                string fullScenePath = Path.Combine(Application.dataPath, "../" + HouseBuilder.ScenePath);
                if (File.Exists(fullScenePath))
                {
                    EditorSceneManager.OpenScene(HouseBuilder.ScenePath);
                }
                else
                {
                    Debug.LogError("[FloodVR] House.unity not found. Run Tools > FloodVR > Build House first.");
                    return;
                }
            }

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
                position = new Vec3Data { x = di.transform.position.x, y = di.transform.position.y, z = di.transform.position.z }
            }).OrderBy(e => e.id).ToArray();

            DamageManifestOutput output = new DamageManifestOutput { items = entries };
            string json = JsonUtility.ToJson(output, true);

            HouseBuilder.EnsureFolder("Assets/StreamingAssets");
            string fullPath = Path.Combine(Application.dataPath, "StreamingAssets/damage_manifest.json");
            File.WriteAllText(fullPath, json);
            AssetDatabase.Refresh();

            Debug.Log($"[FloodVR] Exported {entries.Length} damage items to {ManifestOutputPath}");
        }
    }
}
