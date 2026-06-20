"""
02_geojson_to_geodataframe.py
==============================
Author: Emmanuel Oyekanlu — Principal Data Engineer

PURPOSE:
    Demonstrate the bridge between the raw `geojson` library and GeoPandas:
      1. Load GeoJSON directly into a GeoDataFrame using gpd.read_file()
      2. Perform attribute filtering (filter by crop_type)
      3. Perform geometric computations (area in hectares via UTM reprojection)
      4. Export filtered subsets back to GeoJSON files
      5. Show the GeoDataFrame ↔ GeoJSON round-trip pattern used in data pipelines

REAL-WORLD CONTEXT:
    A typical agricultural data pipeline step:
      → Input:  raw farm boundary GeoJSON from a farmer portal upload
      → Step 1: Load into GeoDataFrame for validation and enrichment
      → Step 2: Filter by attribute (e.g., only process irrigated corn fields)
      → Step 3: Compute area in hectares (reproject to UTM, calc, reproject back)
      → Step 4: Spatial join with county/district boundaries
      → Step 5: Write enriched subset back to GeoJSON for downstream consumers

    The same pattern applies in AGV systems:
      → Load zone configuration GeoJSON
      → Filter to only active zones for the current shift
      → Export filtered zone set to the fleet controller

USAGE:
    python 02_geojson_to_geodataframe.py
"""

import os
import json
import geopandas as gpd
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH  = os.path.join(SCRIPT_DIR, "data", "farm_fields.geojson")
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "data")


def print_section(title: str) -> None:
    width = 65
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


# ---------------------------------------------------------------------------
# SECTION 1: Load GeoJSON into a GeoDataFrame
# ---------------------------------------------------------------------------
print_section("SECTION 1: GeoJSON → GeoDataFrame")

# gpd.read_file() is the universal loader for all geospatial formats.
# For GeoJSON specifically: it parses the FeatureCollection,
# converts each Feature's properties into DataFrame columns,
# and puts each Feature's geometry into the special 'geometry' column.
# The CRS is set to EPSG:4326 (WGS84) automatically for GeoJSON.

gdf = gpd.read_file(INPUT_PATH)

print(f"Loaded: {INPUT_PATH}")
print(f"Type:   {type(gdf).__name__}")
print(f"Shape:  {gdf.shape}  ← ({gdf.shape[0]} rows, {gdf.shape[1]} columns)")
print(f"CRS:    {gdf.crs}")
print()
print("Columns:")
for col in gdf.columns:
    dtype = str(gdf[col].dtype)
    sample = repr(gdf[col].iloc[0])[:40]
    print(f"  {col:<22} dtype={dtype:<12} example={sample}")

print()
print("First 5 rows (key columns):")
print(gdf[['field_id', 'crop_type', 'area_ha', 'irrigation_type', 'farmer']].to_string())

# ---------------------------------------------------------------------------
# SECTION 2: Attribute Filtering — Multiple Patterns
# ---------------------------------------------------------------------------
print_section("SECTION 2: Attribute Filtering")

# Pattern 1: Filter by single value (equality)
corn_fields = gdf[gdf['crop_type'] == 'corn'].copy()
print(f"Corn fields only: {len(corn_fields)} / {len(gdf)} features")
print(corn_fields[['field_id', 'crop_type', 'area_ha']].to_string())

# Pattern 2: Filter by multiple values (.isin())
grain_crops = gdf[gdf['crop_type'].isin(['corn', 'wheat', 'soy'])].copy()
print(f"\nGrain crops (corn/wheat/soy): {len(grain_crops)} / {len(gdf)} features")

# Pattern 3: Filter by numeric condition
large_fields = gdf[gdf['area_ha'] > 20.0].copy()
print(f"\nLarge fields (> 20 ha): {len(large_fields)} / {len(gdf)} features")
print(large_fields[['field_id', 'crop_type', 'area_ha']].to_string())

# Pattern 4: Compound filter — drip-irrigated corn fields
drip_corn = gdf[(gdf['crop_type'] == 'corn') & (gdf['irrigation_type'] == 'drip')].copy()
print(f"\nDrip-irrigated corn: {len(drip_corn)} / {len(gdf)} features")

# Pattern 5: Filter with string contains (farmer name search)
cv_growers = gdf[gdf['farmer'].str.contains("Central Valley", case=False, na=False)].copy()
print(f"\nCentral Valley Growers fields: {len(cv_growers)} features")
print(cv_growers[['field_id', 'crop_type', 'area_ha', 'farmer']].to_string())

# ---------------------------------------------------------------------------
# SECTION 3: Geometric Computations
# ---------------------------------------------------------------------------
print_section("SECTION 3: Geometric Computations")

# CRITICAL: We must reproject to a metric CRS before computing area.
# For the Fresno, CA area: UTM Zone 10N (EPSG:32610) is appropriate.
# UTM Zone 11N (EPSG:32611) also covers this area — check centroid longitude.

centroid_lon = gdf.geometry.centroid.x.mean()
print(f"Mean centroid longitude: {centroid_lon:.4f}°")
print(f"  → Longitude < -120° → UTM Zone 10N (EPSG:32610)")
print(f"  → -120° < Longitude < -114° → UTM Zone 11N (EPSG:32611)")
print(f"  → Fresno at ~-119.7° → Use EPSG:32610 ✓")
print()

# Reproject to UTM Zone 10N
gdf_utm = gdf.to_crs("EPSG:32610")

# Compute geometric properties in the projected CRS
gdf_utm['area_ha_computed'] = gdf_utm.geometry.area / 10_000     # m² → ha
gdf_utm['perimeter_m']      = gdf_utm.geometry.length             # meters
gdf_utm['compactness']      = (
    4 * 3.14159 * gdf_utm.geometry.area
    / (gdf_utm.geometry.length ** 2)
)   # Polsby-Popper ratio: 1.0 = perfect circle, < 0.5 = irregular

# Transfer computed columns back to WGS84 GeoDataFrame for reporting
gdf['area_ha_computed'] = gdf_utm['area_ha_computed']
gdf['perimeter_m']      = gdf_utm['perimeter_m']
gdf['compactness']      = gdf_utm['compactness']

print("Geometric metrics (UTM-based, accurate):")
print(f"{'Field':>8} {'Reported ha':>12} {'Computed ha':>12} {'Perim (m)':>11} {'Compact':>9}")
print("-" * 58)
for _, row in gdf.iterrows():
    diff = row['area_ha_computed'] - row['area_ha']
    flag = "  ← CHECK" if abs(diff) > 2.0 else ""
    print(f"{row['field_id']:>8} {row['area_ha']:>12.2f} {row['area_ha_computed']:>12.4f} "
          f"{row['perimeter_m']:>11.1f} {row['compactness']:>9.4f}{flag}")

print()
print(f"Total farm area (computed): {gdf['area_ha_computed'].sum():.2f} ha")
print(f"Mean compactness:           {gdf['compactness'].mean():.4f}")
print("  (A square has compactness ≈ 0.785; rectangles are lower)")

# ---------------------------------------------------------------------------
# SECTION 4: Group-By Operations (pandas-style)
# ---------------------------------------------------------------------------
print_section("SECTION 4: Group-By Aggregation")

# Because GeoDataFrame inherits from DataFrame, all pandas groupby ops work.
# Just be careful: groupby on a GeoDataFrame returns a DataFrameGroupBy,
# not a GeoDataFrame (the geometry column is lost in aggregation unless
# you use dissolve() which handles it correctly).

print("Area by crop type:")
area_by_crop = (
    gdf
    .groupby('crop_type')
    .agg(
        n_fields      = ('field_id', 'count'),
        total_ha      = ('area_ha_computed', 'sum'),
        mean_ha       = ('area_ha_computed', 'mean'),
        mean_yield    = ('yield_t_ha', 'mean'),
    )
    .round(2)
)
print(area_by_crop.to_string())

print()
print("Area by irrigation type:")
area_by_irr = (
    gdf
    .groupby('irrigation_type')
    .agg(
        n_fields  = ('field_id', 'count'),
        total_ha  = ('area_ha_computed', 'sum'),
        mean_ha   = ('area_ha_computed', 'mean'),
    )
    .round(2)
)
print(area_by_irr.to_string())

# ---------------------------------------------------------------------------
# SECTION 5: Spatial Dissolve — Merge by Attribute
# ---------------------------------------------------------------------------
print_section("SECTION 5: Dissolve — Merge Polygons by Attribute")

# dissolve() is GeoPandas' equivalent of groupby + spatial union.
# It merges all polygons with the same attribute value into one geometry.
# Use case: Create a "corn belt" polygon by unioning all corn fields.

gdf_utm['area_ha_computed'] = gdf_utm.geometry.area / 10_000

# Dissolve by crop_type: union all polygons with the same crop type
dissolved_by_crop = gdf_utm.dissolve(
    by='crop_type',
    aggfunc={
        'area_ha_computed': 'sum',
        'field_id': 'count',
        'yield_t_ha': 'mean',
    }
)

print("Dissolved by crop_type:")
print(dissolved_by_crop[['area_ha_computed', 'field_id', 'yield_t_ha']].rename(
    columns={'field_id': 'n_fields', 'yield_t_ha': 'mean_yield_t_ha'}
).round(2).to_string())

# ---------------------------------------------------------------------------
# SECTION 6: Exporting Filtered GeoDataFrames to GeoJSON
# ---------------------------------------------------------------------------
print_section("SECTION 6: Export Filtered GeoDataFrame to GeoJSON")

# GeoDataFrame.to_file() writes spatial data.
# For GeoJSON output: driver='GeoJSON' (auto-detected from .geojson extension too).
# IMPORTANT: must reproject to WGS84 (EPSG:4326) before writing GeoJSON,
#            because GeoJSON is always in WGS84 per RFC 7946.

# Export 1: Corn fields only (back to WGS84 for export)
corn_export = gdf[gdf['crop_type'] == 'corn'].copy()
# Add computed columns before export
corn_export = corn_export[['field_id', 'crop_type', 'area_ha',
                             'area_ha_computed', 'perimeter_m', 'compactness',
                             'irrigation_type', 'farmer', 'yield_t_ha',
                             'planting_date', 'harvest_date', 'geometry']]

corn_output_path = os.path.join(OUTPUT_DIR, "corn_fields_filtered.geojson")
corn_export.to_file(corn_output_path, driver='GeoJSON')
print(f"Exported corn fields: {corn_output_path}")
print(f"  Features: {len(corn_export)}")
print(f"  File size: {os.path.getsize(corn_output_path) / 1024:.1f} KB")

# Export 2: Large fields only (area > 20 ha)
large_export = gdf[gdf['area_ha_computed'] > 20.0].copy()
large_output_path = os.path.join(OUTPUT_DIR, "large_fields_filtered.geojson")
large_export.to_file(large_output_path, driver='GeoJSON')
print(f"\nExported large fields (>20 ha): {large_output_path}")
print(f"  Features: {len(large_export)}")

# Export 3: Enriched full dataset (all fields with computed metrics)
enriched_output_path = os.path.join(OUTPUT_DIR, "farm_fields_enriched.geojson")
gdf.to_file(enriched_output_path, driver='GeoJSON')
print(f"\nExported enriched full dataset: {enriched_output_path}")
print(f"  Features: {len(gdf)}")
print(f"  Columns:  {list(gdf.columns)}")

# ---------------------------------------------------------------------------
# SECTION 7: GeoDataFrame → GeoJSON String (for API responses)
# ---------------------------------------------------------------------------
print_section("SECTION 7: GeoDataFrame → GeoJSON String (API Pattern)")

# In a web API (FastAPI, Flask), you need to return GeoJSON as a JSON string,
# not write to a file. GeoDataFrame.to_json() returns the GeoJSON string directly.

# Filter to drip-irrigated fields
drip_fields = gdf[gdf['irrigation_type'] == 'drip'].copy()
drip_fields = drip_fields[['field_id', 'crop_type', 'area_ha_computed',
                             'irrigation_type', 'geometry']]

geojson_string = drip_fields.to_json(indent=2)
print("GeoJSON string snippet (drip-irrigated fields):")
print(geojson_string[:400])
print("  ...")

# Parse back to dict for inspection
geojson_dict = json.loads(geojson_string)
print(f"\nParsed back: {geojson_dict['type']} with "
      f"{len(geojson_dict['features'])} features")
print("This is the exact format returned by a REST API endpoint serving GeoJSON.")

print_section("Script Complete")
print("Patterns demonstrated:")
print("  gpd.read_file()           → GeoJSON to GeoDataFrame")
print("  gdf[condition]            → attribute-based filtering")
print("  gdf.to_crs()              → reproject for metric calculations")
print("  .geometry.area / 10_000  → area in hectares")
print("  .groupby().agg()          → aggregate statistics per group")
print("  .dissolve(by=)            → union geometries by attribute")
print("  .to_file(driver='GeoJSON')→ write to GeoJSON file")
print("  .to_json()                → GeoJSON string for API response")
