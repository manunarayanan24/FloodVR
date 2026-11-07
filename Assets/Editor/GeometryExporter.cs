using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace FloodVR
{
    [Serializable]
    public class LengthValue
    {
        public float m;
        public float ft;
        public LengthValue(float meters) { m = meters; ft = meters * 3.28084f; }
    }

    [Serializable]
    public class AreaValue
    {
        public float m2;
        public float ft2;
        public AreaValue(float squareMeters) { m2 = squareMeters; ft2 = squareMeters * 10.7639f; }
    }

    [Serializable]
    public class GeoPoint
    {
        public float x, z;
        public GeoPoint(float x, float z) { this.x = x; this.z = z; }
    }

    [Serializable]
    public class GeoOpening
    {
        public string id, type;
        public LengthValue width;
        public LengthValue height;
        public LengthValue sill;
    }

    [Serializable]
    public class GeoWall
    {
        public string edge; // south|north|west|east
        public string wallId;
        public GeoPoint start;
        public GeoPoint end;
        public LengthValue length;
        public LengthValue height;
        public GeoOpening[] openings;
    }

    [Serializable]
    public class GeoRoom
    {
        public string id, label;
        public GeoPoint[] floorPolygon;
        public AreaValue floorArea;
        public LengthValue ceilingHeight;
        public GeoWall[] walls;
        public AreaValue wallAreaBelowWaterline;
        public AreaValue floodCutDrywallArea;
    }

    [Serializable]
    public class HouseGeometry
    {
        public LengthValue waterlineHeight;
        public LengthValue floodCutHeight;
        public GeoRoom[] rooms;
    }

    public static class GeometryExporter
    {
        public const string OutputPath = "contracts/samples/house_geometry.json";
        private const float FloodCutMarginM = 0.6f;

        [MenuItem("Tools/FloodVR/Export Geometry")]
        public static void ExportGeometry()
        {
            HouseLayout layout = HouseBuilder.LoadLayout();
            if (layout == null) return;

            DamageManifestInput damage = DamageBuilder.LoadDamage();
            float waterlineHeight = 0.9f;
            if (damage?.items != null)
            {
                DamageItemData wl = damage.items.FirstOrDefault(i => i.effect != null && i.effect.type == "waterline");
                if (wl != null) waterlineHeight = wl.effect.heightM;
            }
            float floodCutHeight = waterlineHeight + FloodCutMarginM;

            List<GeoRoom> rooms = new();
            foreach (RoomData room in layout.rooms)
            {
                rooms.Add(BuildRoomGeometry(layout, room, waterlineHeight, floodCutHeight));
            }

            HouseGeometry geo = new HouseGeometry
            {
                waterlineHeight = new LengthValue(waterlineHeight),
                floodCutHeight = new LengthValue(floodCutHeight),
                rooms = rooms.ToArray()
            };

            string json = JsonUtility.ToJson(geo, true);
            string repoRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            string outDir = Path.Combine(repoRoot, "contracts", "samples");
            Directory.CreateDirectory(outDir);
            string fullPath = Path.Combine(outDir, "house_geometry.json");
            File.WriteAllText(fullPath, json);

            Debug.Log($"[FloodVR] Exported geometry for {rooms.Count} rooms to {OutputPath}");
        }

        private static GeoRoom BuildRoomGeometry(HouseLayout layout, RoomData room, float waterlineHeight, float floodCutHeight)
        {
            float wallHeight = layout.house.wallHeight;

            (string edge, float constant, bool isZConstant, float rangeMin, float rangeMax)[] edges =
            {
                ("south", room.minZ, true, room.minX, room.maxX),
                ("north", room.maxZ, true, room.minX, room.maxX),
                ("west", room.minX, false, room.minZ, room.maxZ),
                ("east", room.maxX, false, room.minZ, room.maxZ),
            };

            List<GeoWall> geoWalls = new();
            float wallAreaBelowWaterline = 0f;
            float floodCutArea = 0f;

            foreach (var edge in edges)
            {
                foreach (WallData wall in layout.walls)
                {
                    bool wallIsZConstant = Mathf.Abs(wall.z1 - wall.z2) < 0.0001f;
                    if (wallIsZConstant != edge.isZConstant) continue;

                    float wallConstant = wallIsZConstant ? wall.z1 : wall.x1;
                    if (Mathf.Abs(wallConstant - edge.constant) > 0.01f) continue;

                    float wallMin = wallIsZConstant ? Mathf.Min(wall.x1, wall.x2) : Mathf.Min(wall.z1, wall.z2);
                    float wallMax = wallIsZConstant ? Mathf.Max(wall.x1, wall.x2) : Mathf.Max(wall.z1, wall.z2);

                    float overlapMin = Mathf.Max(wallMin, edge.rangeMin);
                    float overlapMax = Mathf.Min(wallMax, edge.rangeMax);
                    if (overlapMax - overlapMin <= 0.001f) continue;

                    GeoPoint startPt = edge.isZConstant ? new GeoPoint(overlapMin, edge.constant) : new GeoPoint(edge.constant, overlapMin);
                    GeoPoint endPt = edge.isZConstant ? new GeoPoint(overlapMax, edge.constant) : new GeoPoint(edge.constant, overlapMax);
                    float length = overlapMax - overlapMin;

                    List<GeoOpening> openings = new();
                    float wallBase = wallIsZConstant ? wall.x1 : wall.z1; // wall data is monotonic increasing in our layout
                    foreach (OpeningData o in wall.openings ?? new OpeningData[0])
                    {
                        float absStart = wallBase + o.start;
                        float absEnd = wallBase + o.end;
                        float clipStart = Mathf.Max(absStart, overlapMin);
                        float clipEnd = Mathf.Min(absEnd, overlapMax);
                        if (clipEnd - clipStart <= 0.001f) continue;

                        float width = clipEnd - clipStart;
                        openings.Add(new GeoOpening
                        {
                            id = o.id,
                            type = o.type,
                            width = new LengthValue(width),
                            height = new LengthValue(o.top - o.bottom),
                            sill = new LengthValue(o.bottom)
                        });

                        wallAreaBelowWaterline -= OverlapArea(width, o.bottom, o.top, 0f, waterlineHeight);
                        floodCutArea -= OverlapArea(width, o.bottom, o.top, 0f, floodCutHeight);
                    }

                    wallAreaBelowWaterline += length * Mathf.Min(waterlineHeight, wallHeight);
                    floodCutArea += length * Mathf.Min(floodCutHeight, wallHeight);

                    geoWalls.Add(new GeoWall
                    {
                        edge = edge.edge,
                        wallId = wall.id,
                        start = startPt,
                        end = endPt,
                        length = new LengthValue(length),
                        height = new LengthValue(wallHeight),
                        openings = openings.ToArray()
                    });
                }
            }

            float floorArea = (room.maxX - room.minX) * (room.maxZ - room.minZ);

            return new GeoRoom
            {
                id = room.id,
                label = room.label,
                floorPolygon = new[]
                {
                    new GeoPoint(room.minX, room.minZ),
                    new GeoPoint(room.maxX, room.minZ),
                    new GeoPoint(room.maxX, room.maxZ),
                    new GeoPoint(room.minX, room.maxZ),
                },
                floorArea = new AreaValue(floorArea),
                ceilingHeight = new LengthValue(wallHeight),
                walls = geoWalls.ToArray(),
                wallAreaBelowWaterline = new AreaValue(Mathf.Max(0f, wallAreaBelowWaterline)),
                floodCutDrywallArea = new AreaValue(Mathf.Max(0f, floodCutArea))
            };
        }

        // Area of an opening's intersection with a vertical height band [bandBottom, bandTop].
        private static float OverlapArea(float width, float openBottom, float openTop, float bandBottom, float bandTop)
        {
            float overlapBottom = Mathf.Max(openBottom, bandBottom);
            float overlapTop = Mathf.Min(openTop, bandTop);
            return overlapTop > overlapBottom ? width * (overlapTop - overlapBottom) : 0f;
        }
    }
}
