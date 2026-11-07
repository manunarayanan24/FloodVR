using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace FloodVR
{
    [Serializable]
    public class ColorData
    {
        public float r, g, b, a = 1f;
        public Color ToColor() => new Color(r, g, b, a);
    }

    [Serializable]
    public class Vec3Data
    {
        public float x, y, z;
        public Vector3 ToVector3() => new Vector3(x, y, z);
    }

    [Serializable]
    public class HouseData
    {
        public float width, depth, wallHeight, wallThickness;
        public ColorData floorColor, ceilingColor, wallColor;
    }

    [Serializable]
    public class RoomData
    {
        public string id, label;
        public float minX, minZ, maxX, maxZ;
    }

    [Serializable]
    public class OpeningData
    {
        public string id, type;
        public float start, end, bottom, top;
    }

    [Serializable]
    public class WallData
    {
        public string id;
        public float x1, z1, x2, z2;
        public OpeningData[] openings;
    }

    [Serializable]
    public class FurnitureData
    {
        public string id, room, shape;
        public Vec3Data pos, size;
        public float rotationY;
        public ColorData color;
    }

    [Serializable]
    public class OutletData
    {
        public string id, room;
        public Vec3Data pos;
        public float rotationY;
        public float heightM;
    }

    [Serializable]
    public class SceneData
    {
        public Vec3Data cameraPos, cameraLookAt, lightRotationEuler;
        public ColorData lightColor;
        public float lightIntensity;
        public ColorData skyColor;
        public ColorData ambientColor;
        public float fogStart;
        public float fogEnd;
    }

    [Serializable]
    public class StandPointData
    {
        public string id;
        public Vec3Data pos, lookAt;
    }

    [Serializable]
    public class SceneTextData
    {
        public string id, targetId, text;
    }

    [Serializable]
    public class OutdoorWaterData
    {
        public float topY, minX, maxX, minZ, maxZ;
        public ColorData color;
    }

    [Serializable]
    public class PuddleData
    {
        public string id;
        public Vec3Data pos;
        public Vec2Data size;
        public ColorData color;
    }

    [Serializable]
    public class Vec2Data
    {
        public float x, z;
    }

    [Serializable]
    public class HouseLayout
    {
        public HouseData house;
        public RoomData[] rooms;
        public WallData[] walls;
        public StandPointData[] standPoints;
        public FurnitureData[] furniture;
        public OutletData[] outlets;
        public SceneTextData[] sceneTexts;
        public OutdoorWaterData outdoorWater;
        public PuddleData[] puddles;
        public SceneData scene;
    }

    public static class HouseBuilder
    {
        public const string HouseRootName = "House";
        public const string ScenePath = "Assets/Scenes/House.unity";
        public const string LayoutJsonPath = "Assets/Data/house_layout.json";
        public const string MaterialsFolder = "Assets/Materials";

        internal static readonly Dictionary<string, Material> materialCache = new();

        [MenuItem("Tools/FloodVR/Build House")]
        public static void BuildHouse()
        {
            HouseLayout layout = LoadLayout();
            if (layout == null) return;

            EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            Scene activeScene = EditorSceneManager.GetActiveScene();

            GameObject existingRoot = GameObject.Find(HouseRootName);
            if (existingRoot != null) UnityEngine.Object.DestroyImmediate(existingRoot);

            GameObject root = new GameObject(HouseRootName);

            EnsureFolder(MaterialsFolder);

            BuildFloor(root.transform, layout.house);
            BuildCeiling(root.transform, layout.house);
            BuildWalls(root.transform, layout);
            BuildStandPoints(root.transform, layout);
            BuildFurniture(root.transform, layout);
            BuildOutlets(root.transform, layout);
            BuildPuddles(root.transform, layout);
            BuildOutdoorWater(root.transform, layout);
            SceneTextBuilder.BuildSceneTexts(layout);
            DamageBuilder.ApplyDamage(root.transform, layout);
            ConfigureCameraAndLight(layout.scene);

            EnsureFolder("Assets/Scenes");
            AssetDatabase.SaveAssets();
            bool saved = EditorSceneManager.SaveScene(activeScene, ScenePath);
            if (saved)
                Debug.Log($"[FloodVR] House built and scene saved to {ScenePath}");
            else
                Debug.LogError("[FloodVR] Failed to save House.unity scene.");
        }

        public static HouseLayout LoadLayout()
        {
            string path = Path.Combine(Application.dataPath, "Data/house_layout.json");
            if (!File.Exists(path))
            {
                Debug.LogError($"[FloodVR] house_layout.json not found at {path}");
                return null;
            }
            string json = File.ReadAllText(path);
            return JsonUtility.FromJson<HouseLayout>(json);
        }

        internal static void EnsureFolder(string assetFolderPath)
        {
            if (AssetDatabase.IsValidFolder(assetFolderPath)) return;
            string parent = Path.GetDirectoryName(assetFolderPath).Replace("\\", "/");
            string leaf = Path.GetFileName(assetFolderPath);
            if (!AssetDatabase.IsValidFolder(parent)) EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, leaf);
        }

        internal static Material GetOrCreateMaterial(Color color, string name)
        {
            if (materialCache.TryGetValue(name, out Material cached))
            {
                cached.color = color;
                return cached;
            }

            string path = $"{MaterialsFolder}/Mat_{name}.mat";
            Material mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (mat == null)
            {
                mat = new Material(Shader.Find("Standard"));
                mat.SetFloat("_Glossiness", 0f);
                mat.SetFloat("_Metallic", 0f);
                mat.color = color;
                AssetDatabase.CreateAsset(mat, path);
            }
            else
            {
                mat.color = color;
                EditorUtility.SetDirty(mat);
            }

            materialCache[name] = mat;
            return mat;
        }

        internal static GameObject CreatePrimitiveChild(PrimitiveType type, string name, Transform parent)
        {
            GameObject go = GameObject.CreatePrimitive(type);
            go.name = name;
            go.transform.SetParent(parent, false);
            return go;
        }

        private static void BuildFloor(Transform root, HouseData house)
        {
            const float thickness = 0.1f;
            GameObject floor = CreatePrimitiveChild(PrimitiveType.Cube, "Floor", root);
            floor.transform.position = new Vector3(house.width / 2f, -thickness / 2f, house.depth / 2f);
            floor.transform.localScale = new Vector3(house.width, thickness, house.depth);
            floor.GetComponent<Renderer>().sharedMaterial = GetOrCreateMaterial(house.floorColor.ToColor(), "Floor");
        }

        private static void BuildCeiling(Transform root, HouseData house)
        {
            const float thickness = 0.1f;
            GameObject ceiling = CreatePrimitiveChild(PrimitiveType.Cube, "Ceiling", root);
            ceiling.transform.position = new Vector3(house.width / 2f, house.wallHeight + thickness / 2f, house.depth / 2f);
            ceiling.transform.localScale = new Vector3(house.width, thickness, house.depth);
            ceiling.GetComponent<Renderer>().sharedMaterial = GetOrCreateMaterial(house.ceilingColor.ToColor(), "Ceiling");
        }

        private static void BuildWalls(Transform root, HouseLayout layout)
        {
            GameObject wallsRoot = new GameObject("Walls");
            wallsRoot.transform.SetParent(root, false);
            Material wallMat = GetOrCreateMaterial(layout.house.wallColor.ToColor(), "Wall");

            foreach (WallData wall in layout.walls)
            {
                BuildWall(wallsRoot.transform, wall, layout.house.wallHeight, layout.house.wallThickness, wallMat);
            }
        }

        private static void BuildWall(Transform parent, WallData wall, float wallHeight, float thickness, Material mat)
        {
            Vector3 p1 = new Vector3(wall.x1, 0f, wall.z1);
            Vector3 p2 = new Vector3(wall.x2, 0f, wall.z2);
            Vector3 delta = p2 - p1;
            float totalLength = delta.magnitude;
            if (totalLength < 0.001f) return;
            Vector3 dir = delta.normalized;
            float angle = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;

            GameObject wallGO = new GameObject($"Wall_{wall.id}");
            wallGO.transform.SetParent(parent, false);

            List<OpeningData> openings = (wall.openings ?? new OpeningData[0])
                .OrderBy(o => o.start)
                .ToList();

            float cursor = 0f;
            int segIndex = 0;
            foreach (OpeningData opening in openings)
            {
                if (opening.start > cursor + 0.0001f)
                {
                    BuildWallSegment(wallGO.transform, p1, dir, angle, cursor, opening.start, 0f, wallHeight, thickness, mat, $"seg_{segIndex++}");
                }

                if (opening.top < wallHeight - 0.0001f)
                {
                    BuildWallSegment(wallGO.transform, p1, dir, angle, opening.start, opening.end, opening.top, wallHeight, thickness, mat, $"header_{opening.id}");
                }

                if (opening.bottom > 0.0001f)
                {
                    BuildWallSegment(wallGO.transform, p1, dir, angle, opening.start, opening.end, 0f, opening.bottom, thickness, mat, $"sill_{opening.id}");
                }

                cursor = opening.end;
            }

            if (cursor < totalLength - 0.0001f)
            {
                BuildWallSegment(wallGO.transform, p1, dir, angle, cursor, totalLength, 0f, wallHeight, thickness, mat, $"seg_{segIndex++}");
            }
        }

        private static void BuildWallSegment(Transform parent, Vector3 p1, Vector3 dir, float angle,
            float segStart, float segEnd, float bottom, float top, float thickness, Material mat, string name)
        {
            float length = segEnd - segStart;
            if (length <= 0.0001f || top - bottom <= 0.0001f) return;

            float centerDist = (segStart + segEnd) / 2f;
            Vector3 pos = p1 + dir * centerDist;
            pos.y = (bottom + top) / 2f;

            GameObject seg = CreatePrimitiveChild(PrimitiveType.Cube, name, parent);
            seg.transform.position = pos;
            seg.transform.rotation = Quaternion.Euler(0f, angle, 0f);
            seg.transform.localScale = new Vector3(thickness, top - bottom, length);
            seg.GetComponent<Renderer>().sharedMaterial = mat;
        }

        private static void BuildStandPoints(Transform root, HouseLayout layout)
        {
            if (layout.standPoints == null) return;
            GameObject standRoot = new GameObject("StandPoints");
            standRoot.transform.SetParent(root, false);

            foreach (StandPointData sp in layout.standPoints)
            {
                GameObject go = new GameObject(sp.id);
                go.transform.SetParent(standRoot.transform, false);
                go.transform.position = sp.pos.ToVector3();
                go.transform.LookAt(sp.lookAt.ToVector3());
            }
        }

        private static void BuildFurniture(Transform root, HouseLayout layout)
        {
            if (layout.furniture == null) return;
            GameObject furnitureRoot = new GameObject("Furniture");
            furnitureRoot.transform.SetParent(root, false);

            foreach (FurnitureData item in layout.furniture)
            {
                PrimitiveType type = item.shape == "cylinder" ? PrimitiveType.Cylinder : PrimitiveType.Cube;
                GameObject go = CreatePrimitiveChild(type, item.id, furnitureRoot.transform);
                go.transform.position = item.pos.ToVector3();
                go.transform.rotation = Quaternion.Euler(0f, item.rotationY, 0f);

                Vector3 size = item.size.ToVector3();
                go.transform.localScale = type == PrimitiveType.Cylinder
                    ? new Vector3(size.x, size.y / 2f, size.z)
                    : size;

                go.GetComponent<Renderer>().sharedMaterial = GetOrCreateMaterial(item.color.ToColor(), item.id);
            }
        }

        private static void BuildOutlets(Transform root, HouseLayout layout)
        {
            if (layout.outlets == null) return;
            GameObject outletsRoot = new GameObject("Outlets");
            outletsRoot.transform.SetParent(root, false);
            Material outletMat = GetOrCreateMaterial(new Color(0.95f, 0.95f, 0.92f), "Outlet");

            foreach (OutletData outlet in layout.outlets)
            {
                GameObject go = CreatePrimitiveChild(PrimitiveType.Cube, outlet.id, outletsRoot.transform);
                go.transform.position = outlet.pos.ToVector3();
                go.transform.rotation = Quaternion.Euler(0f, outlet.rotationY, 0f);
                go.transform.localScale = new Vector3(0.02f, 0.11f, 0.07f);
                go.GetComponent<Renderer>().sharedMaterial = outletMat;
            }
        }

        private static void BuildPuddles(Transform root, HouseLayout layout)
        {
            if (layout.puddles == null) return;
            GameObject puddlesRoot = new GameObject("Puddles");
            puddlesRoot.transform.SetParent(root, false);

            foreach (PuddleData p in layout.puddles)
            {
                GameObject go = CreatePrimitiveChild(PrimitiveType.Cube, p.id, puddlesRoot.transform);
                go.transform.position = p.pos.ToVector3();
                go.transform.localScale = new Vector3(p.size.x, 0.005f, p.size.z);
                Material mat = GetOrCreateMaterial(p.color.ToColor(), p.id);
                mat.SetFloat("_Glossiness", 0.6f); // cheap stand-in for reflective standing water
                go.GetComponent<Renderer>().sharedMaterial = mat;
            }
        }

        // Builds the outdoor water as a frame of 4 slabs AROUND the house
        // footprint (not a single slab under it) so it never pokes up through
        // the floor on the inside -- only visible from outside, through windows.
        private static void BuildOutdoorWater(Transform root, HouseLayout layout)
        {
            OutdoorWaterData w = layout.outdoorWater;
            if (w == null) return;

            const float thickness = 0.1f;
            GameObject waterRoot = new GameObject("OutdoorFloodWater");
            waterRoot.transform.SetParent(root, false);
            Material mat = GetOrCreateMaterial(w.color.ToColor(), "OutdoorFloodWater");
            mat.SetFloat("_Glossiness", 0.5f);

            float houseW = layout.house.width;
            float houseD = layout.house.depth;
            float y = w.topY - thickness / 2f;

            AddWaterSlab(waterRoot.transform, mat, w.minX, 0f, w.minZ, w.maxZ, y, thickness, "West");
            AddWaterSlab(waterRoot.transform, mat, houseW, w.maxX, w.minZ, w.maxZ, y, thickness, "East");
            AddWaterSlab(waterRoot.transform, mat, 0f, houseW, w.minZ, 0f, y, thickness, "South");
            AddWaterSlab(waterRoot.transform, mat, 0f, houseW, houseD, w.maxZ, y, thickness, "North");
        }

        private static void AddWaterSlab(Transform parent, Material mat, float x1, float x2, float z1, float z2, float y, float thickness, string name)
        {
            if (x2 - x1 <= 0.001f || z2 - z1 <= 0.001f) return;
            GameObject slab = CreatePrimitiveChild(PrimitiveType.Cube, $"Water_{name}", parent);
            slab.transform.position = new Vector3((x1 + x2) / 2f, y, (z1 + z2) / 2f);
            slab.transform.localScale = new Vector3(x2 - x1, thickness, z2 - z1);
            slab.GetComponent<Renderer>().sharedMaterial = mat;
        }

        private static void ConfigureCameraAndLight(SceneData sceneData)
        {
            if (sceneData == null) return;

            Color skyColor = sceneData.skyColor != null ? sceneData.skyColor.ToColor() : new Color(0.6f, 0.6f, 0.6f);

            Camera cam = Camera.main;
            if (cam != null)
            {
                cam.transform.position = sceneData.cameraPos.ToVector3();
                cam.transform.LookAt(sceneData.cameraLookAt.ToVector3());
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = skyColor;
            }

            Light light = UnityEngine.Object.FindFirstObjectByType<Light>();
            if (light != null)
            {
                light.type = LightType.Directional;
                light.shadows = LightShadows.None;
                light.color = sceneData.lightColor.ToColor();
                light.intensity = sceneData.lightIntensity;
                light.transform.rotation = Quaternion.Euler(sceneData.lightRotationEuler.ToVector3());
            }

            // Cheap grey-overcast look: solid-color sky (no skybox render cost),
            // flat ambient instead of skybox-sampled GI, and fog to hide the
            // open-ended exterior -- all inexpensive for WebGL on an iPhone.
            RenderSettings.skybox = null;
            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.ambientLight = sceneData.ambientColor != null ? sceneData.ambientColor.ToColor() : skyColor * 0.7f;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = skyColor;
            RenderSettings.fogStartDistance = sceneData.fogStart > 0f ? sceneData.fogStart : 4f;
            RenderSettings.fogEndDistance = sceneData.fogEnd > 0f ? sceneData.fogEnd : 32f;
        }
    }
}
