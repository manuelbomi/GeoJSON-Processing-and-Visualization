"""
01_geojson_read_write.py
=========================
Author: Emmanuel Oyekanlu — Principal Data Engineer

PURPOSE:
    Demonstrate how to use the `geojson` Python library to:
      1. Load a GeoJSON file and inspect its structure
      2. Navigate the FeatureCollection / Feature / geometry hierarchy
      3. Access and modify feature properties
      4. Add a new Feature programmatically
      5. Write the updated FeatureCollection back to a file with formatting

    This script uses the `geojson` library (not GeoPandas) to work at the
    raw JSON level — essential for writing validators, API serializers, and
    ETL ingestion handlers that need to understand GeoJSON's exact structure.

REAL-WORLD CONTEXT:
    In an agricultural data platform:
      - Farm apps upload GeoJSON field boundaries via a REST API
      - Your ingestion service validates the raw GeoJSON before inserting to PostGIS
      - You need to add computed attributes (area_ha, county_fips) to each feature
        before re-serving the data
      - You write test fixtures by constructing GeoJSON Features programmatically

    In an AGV fleet system:
      - Zone configurations are stored as GeoJSON files in version control
      - A deployment tool reads, validates, adds metadata, and writes back
        the updated zone config before uploading to the fleet management server

USAGE:
    python 01_geojson_read_write.py

OUTPUT:
    - Prints inspection results to stdout
    - Writes data/farm_fields_updated.geojson (original + 1 new feature)
"""

import os
import json
import copy
from datetime import datetime
import geojson
from geojson import (
    Feature,
    FeatureCollection,
    Polygon,
    Point,
    MultiPolygon,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH  = os.path.join(SCRIPT_DIR, "data", "farm_fields.geojson")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "farm_fields_updated.geojson")


def print_section(title: str) -> None:
    width = 65
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


# ---------------------------------------------------------------------------
# SECTION 1: Loading a GeoJSON file with the `geojson` library
# ---------------------------------------------------------------------------
print_section("SECTION 1: Loading GeoJSON with the geojson Library")

# geojson.load() reads a GeoJSON file and returns typed Python objects.
# Unlike json.load(), the returned objects are geojson-specific types:
#   FeatureCollection, Feature, Point, Polygon, etc.
# These objects inherit from dict, so all standard dict operations work.

with open(INPUT_PATH, "r", encoding="utf-8") as f:
    fc = geojson.load(f)

# The top-level object is a FeatureCollection
print(f"Type of loaded object:   {type(fc).__name__}")
print(f"  → inherits from dict:  {isinstance(fc, dict)}")
print(f"  → GeoJSON type field:  {fc['type']}")
print(f"  → Number of features:  {len(fc['features'])}")
print(f"  → geojson.is_valid():  {geojson.is_valid(fc)['valid']}")

# ---------------------------------------------------------------------------
# SECTION 2: Navigating the FeatureCollection hierarchy
# ---------------------------------------------------------------------------
print_section("SECTION 2: FeatureCollection Hierarchy")

print("""
GeoJSON Object Hierarchy:
  FeatureCollection
    └── features: [ Feature, Feature, ... ]
                   └── geometry: { type: "Polygon", coordinates: [...] }
                   └── properties: { field_id: "FF-001", crop_type: "corn", ... }
                   └── id: "FF-001"  (optional)
""")

print("Features in FeatureCollection:")
for i, feature in enumerate(fc['features']):
    # Each feature is a geojson.Feature object (dict subclass)
    fid        = feature.get('id', 'no-id')
    geom_type  = feature['geometry']['type']
    props      = feature['properties']
    field_id   = props.get('field_id', '?')
    crop_type  = props.get('crop_type', '?')
    area_ha    = props.get('area_ha', '?')
    irrig      = props.get('irrigation_type', '?')

    print(f"  [{i}] id={fid}  field={field_id}  crop={crop_type:8s}  "
          f"area={area_ha:5.1f} ha  irrigation={irrig}")

# ---------------------------------------------------------------------------
# SECTION 3: Accessing geometry coordinates
# ---------------------------------------------------------------------------
print_section("SECTION 3: Geometry Access and Coordinate Inspection")

# Geometry access: feature['geometry'] is a dict (or geojson.Polygon, etc.)
first_feature = fc['features'][0]
geom = first_feature['geometry']

print(f"First feature geometry type: {geom['type']}")
print()

# For a Polygon: coordinates = [ exterior_ring, hole1, hole2, ... ]
#   exterior_ring = [ [lon, lat], [lon, lat], ... ]
# The exterior ring is always coordinates[0]
exterior_ring = geom['coordinates'][0]
n_vertices = len(exterior_ring)
print(f"Exterior ring has {n_vertices} vertices (includes closing repeat)")
print("Vertices:")
for v in exterior_ring:
    print(f"  [lon={v[0]:.6f}, lat={v[1]:.6f}]")

# Count holes (interior rings) — indices 1, 2, ... in coordinates list
n_holes = len(geom['coordinates']) - 1
print(f"\nNumber of holes (interior rings): {n_holes}")

# Compute bounding box manually from coordinates
lons = [v[0] for v in exterior_ring]
lats = [v[1] for v in exterior_ring]
print(f"\nManual bounding box:")
print(f"  West:  {min(lons):.6f}°   East:  {max(lons):.6f}°")
print(f"  South: {min(lats):.6f}°   North: {max(lats):.6f}°")

# ---------------------------------------------------------------------------
# SECTION 4: Iterating over properties
# ---------------------------------------------------------------------------
print_section("SECTION 4: Properties Inspection")

print("All properties of the first feature:")
for key, val in first_feature['properties'].items():
    print(f"  {key:<20} = {val!r}")

print()
# Aggregate across all features
crop_types = [f['properties']['crop_type'] for f in fc['features']]
areas      = [f['properties']['area_ha'] for f in fc['features']]
total_area = sum(areas)
mean_area  = total_area / len(areas)

print(f"Crop types present: {sorted(set(crop_types))}")
print(f"Total area:   {total_area:.1f} ha")
print(f"Mean area:    {mean_area:.1f} ha")
print(f"Largest field: {max(areas):.1f} ha")
print(f"Smallest field: {min(areas):.1f} ha")

# ---------------------------------------------------------------------------
# SECTION 5: Modifying properties — add a computed field
# ---------------------------------------------------------------------------
print_section("SECTION 5: Adding Computed Properties to Features")

# Deep copy the FeatureCollection so we don't modify the original in memory.
# In production ETL, you'd typically create a new FeatureCollection from scratch
# rather than mutating the input, but a deep copy is acceptable for a pipeline step.
fc_updated = copy.deepcopy(fc)

# Add metadata and computed attributes to each feature
ingestion_ts = datetime.utcnow().isoformat() + "Z"

for feature in fc_updated['features']:
    props = feature['properties']

    # 1. Ingestion timestamp — audit trail for the pipeline
    props['ingested_at'] = ingestion_ts

    # 2. Data source tag — for lineage tracking
    props['data_source'] = "fresno_county_gis_export_v2"

    # 3. Area bucket — categorical attribute for filtering
    area = props.get('area_ha', 0)
    if area < 10:
        props['size_class'] = "small"
    elif area < 20:
        props['size_class'] = "medium"
    else:
        props['size_class'] = "large"

    # 4. Has_irrigation flag (boolean from irrigation_type != 'none')
    irr_type = props.get('irrigation_type', 'none')
    props['has_irrigation'] = irr_type.lower() != 'none'

print("Computed properties added to each feature:")
print("  ingested_at    ← UTC timestamp for audit trail")
print("  data_source    ← lineage tag")
print("  size_class     ← 'small'|'medium'|'large' based on area_ha")
print("  has_irrigation ← bool: True if irrigation_type != 'none'")
print()
# Show first feature's updated properties
print("First feature properties after update:")
for k, v in fc_updated['features'][0]['properties'].items():
    print(f"  {k:<22} = {v!r}")

# ---------------------------------------------------------------------------
# SECTION 6: Adding a new Feature programmatically
# ---------------------------------------------------------------------------
print_section("SECTION 6: Adding a New Feature Programmatically")

# Scenario: A new field has been surveyed and its GPS corner coordinates
# collected in the field. We create a GeoJSON Feature and append it to the
# FeatureCollection before writing back to the file.

new_field_coordinates = [
    [-119.6580, 36.7000],
    [-119.6480, 36.7000],
    [-119.6480, 36.7080],
    [-119.6580, 36.7080],
    [-119.6580, 36.7000],   # close the ring
]

# geojson.Polygon expects coordinates as a list of rings (exterior + holes)
# For a simple polygon with no holes: [exterior_ring]
new_geometry = Polygon([new_field_coordinates])

new_properties = {
    "field_id":        "FF-009",
    "crop_type":       "corn",
    "area_ha":         8.9,   # will be recalculated by server
    "irrigation_type": "drip",
    "farmer":          "Eastside Farm Collective",
    "soil_type":       "sandy_loam",
    "yield_t_ha":      None,   # null — not yet harvested
    "planting_date":   "2024-05-01",
    "harvest_date":    None,   # not yet harvested
    "ingested_at":     ingestion_ts,
    "data_source":     "field_survey_tablet_upload",
    "size_class":      "small",
    "has_irrigation":  True,
}

# geojson.Feature constructor: Feature(geometry=..., properties=..., id=...)
new_feature = Feature(
    geometry=new_geometry,
    properties=new_properties,
    id="FF-009",
)

# Validate the new feature before adding it
validation = geojson.is_valid(new_feature)
print(f"New feature validity: {validation['valid']}")
if not validation['valid']:
    print(f"  Errors: {validation['message']}")
else:
    print(f"  Geometry type: {new_feature['geometry']['type']}")
    print(f"  Field ID: {new_feature['properties']['field_id']}")

# Append to the FeatureCollection's features list
fc_updated['features'].append(new_feature)
print(f"\nFeatureCollection now has {len(fc_updated['features'])} features "
      f"(was {len(fc['features'])})")

# ---------------------------------------------------------------------------
# SECTION 7: Writing the updated GeoJSON to a file
# ---------------------------------------------------------------------------
print_section("SECTION 7: Writing GeoJSON to File")

# geojson.dumps() serializes to a JSON string with optional indentation.
# We use indent=2 for readability; production APIs often use indent=None (compact).

# Option A: Using geojson.dump() directly
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    geojson.dump(
        fc_updated,
        f,
        indent=2,
        ensure_ascii=False,  # allow UTF-8 characters in farmer names etc.
        sort_keys=False,     # preserve the key order (type, id, geometry, properties)
    )

file_size_kb = os.path.getsize(OUTPUT_PATH) / 1024
print(f"Written to: {OUTPUT_PATH}")
print(f"File size: {file_size_kb:.1f} KB")
print(f"Features: {len(fc_updated['features'])}")

# Verify round-trip: reload and confirm feature count and validity
with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
    fc_reloaded = geojson.load(f)

print(f"\nRound-trip verification:")
print(f"  Reloaded features: {len(fc_reloaded['features'])}")
print(f"  Is valid GeoJSON:  {geojson.is_valid(fc_reloaded)['valid']}")
print(f"  New feature present: "
      f"{'FF-009' in [ft['properties']['field_id'] for ft in fc_reloaded['features']]}")

# Option B: Using json.dumps() for more control (e.g., custom float precision)
# geojson objects are dict subclasses so json.dumps() works too
geojson_str = json.dumps(fc_updated, indent=2, ensure_ascii=False)
char_count = len(geojson_str)
print(f"\nJSON string character count: {char_count:,}")
print(f"Approx. uncompressed size:   {char_count / 1024:.1f} KB")
print(f"With gzip compression:       {char_count / 1024 / 5:.1f} KB  (typical 5:1 ratio for JSON)")

print_section("Script Complete")
print("Key takeaways:")
print("  1. geojson.load() returns typed objects that inherit from dict")
print("  2. Feature hierarchy: FeatureCollection → Feature → geometry + properties")
print("  3. Polygon coordinates = [[exterior_ring], [hole1], ...]")
print("  4. geojson.Feature() / Polygon() create valid GeoJSON structures")
print("  5. geojson.is_valid() validates before writing")
print("  6. geojson.dump() writes formatted GeoJSON with proper encoding")
print("\nNext: Run 02_geojson_to_geodataframe.py")
