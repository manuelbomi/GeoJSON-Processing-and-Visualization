"""
04_geojson_spatial_queries.py
==============================
Author: Emmanuel Oyekanlu — Principal Data Engineer

PURPOSE:
    Load two GeoJSON layers (farm fields and irrigation districts), perform
    a spatial join to determine which fields overlap which irrigation zones,
    compute overlap percentages, and export an enriched GeoJSON with the
    spatial relationship embedded as properties.

REAL-WORLD CONTEXT:
    This is a classic geospatial data engineering task: the "spatial join and
    attribute transfer" pattern. Agricultural examples:

    1. WATER RIGHTS COMPLIANCE:
       "Which irrigation district is each field in? What is each field's
        total water allocation based on district rates?"
       → Spatial join: fields ∩ irrigation_zones → assign water_source, district_code

    2. SUBSIDY ELIGIBILITY:
       "Which county is each field in? What USDA FSA program area is it assigned to?"
       → Spatial join: fields ∩ county_boundaries → assign fips_code, fsa_district

    3. AGV ZONE MANAGEMENT:
       "Which manager zone does each AGV event fall in?"
       → Spatial join: events_points ∩ zone_polygons → assign zone_id, manager

    4. MULTI-DISTRICT FIELDS:
       "Some fields straddle two irrigation districts. What percentage of each
        field falls in each district? How do we apportion water billing?"
       → Intersection + area calculation → overlap_pct by district

USAGE:
    python 04_geojson_spatial_queries.py

OUTPUT:
    data/farm_fields_enriched_irrigation.geojson — fields with irrigation zone
    attributes added, including overlap percentages for multi-district fields.
"""

import os
import json
import geopandas as gpd
import pandas as pd
import numpy as np

SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
FIELDS_PATH      = os.path.join(SCRIPT_DIR, "data", "farm_fields.geojson")
IRRIGATION_PATH  = os.path.join(SCRIPT_DIR, "data", "irrigation_zones.geojson")
OUTPUT_PATH      = os.path.join(SCRIPT_DIR, "data", "farm_fields_enriched_irrigation.geojson")


def print_section(title: str) -> None:
    width = 65
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


# ---------------------------------------------------------------------------
# STEP 1: Load both GeoJSON layers
# ---------------------------------------------------------------------------
print_section("STEP 1: Load GeoJSON Layers")

fields     = gpd.read_file(FIELDS_PATH)
irrigation = gpd.read_file(IRRIGATION_PATH)

print(f"Farm fields:        {len(fields)} features")
print(f"  Columns: {list(fields.columns)}")
print(f"  CRS:     {fields.crs}")
print()
print(f"Irrigation zones:   {len(irrigation)} features")
print(f"  Columns: {list(irrigation.columns)}")
print(f"  CRS:     {irrigation.crs}")

# Verify CRS match — CRITICAL before any spatial join
print(f"\nCRS match: {fields.crs == irrigation.crs}")
if fields.crs != irrigation.crs:
    print("  ! Reprojecting irrigation to match fields CRS")
    irrigation = irrigation.to_crs(fields.crs)

# ---------------------------------------------------------------------------
# STEP 2: Overview spatial query — bounding box overlap check
# ---------------------------------------------------------------------------
print_section("STEP 2: Spatial Extent Overview")

f_bounds = fields.total_bounds
i_bounds = irrigation.total_bounds

print(f"Fields extent:      lon [{f_bounds[0]:.4f}, {f_bounds[2]:.4f}], "
      f"lat [{f_bounds[1]:.4f}, {f_bounds[3]:.4f}]")
print(f"Irrigation extent:  lon [{i_bounds[0]:.4f}, {i_bounds[2]:.4f}], "
      f"lat [{i_bounds[1]:.4f}, {i_bounds[3]:.4f}]")

# Quick bbox overlap check
bbox_overlap = not (
    f_bounds[2] < i_bounds[0] or i_bounds[2] < f_bounds[0] or
    f_bounds[3] < i_bounds[1] or i_bounds[3] < f_bounds[1]
)
print(f"Bounding boxes overlap: {bbox_overlap}")

# ---------------------------------------------------------------------------
# STEP 3: Simple spatial join (left join — keep all fields)
# ---------------------------------------------------------------------------
print_section("STEP 3: Simple Spatial Join (fields ∩ irrigation zones)")

# gpd.sjoin() performs the spatial join.
# how='left'     → keep all fields even if no irrigation zone match
# predicate      → 'intersects' catches all fields that touch or overlap a zone
#                  'within' would only catch fields 100% inside a zone

# First, rename irrigation columns to avoid collision with field columns
irrigation_join = irrigation[['zone_id', 'zone_name', 'water_source',
                               'district_code', 'annual_allocation_af',
                               'delivery_method', 'geometry']].copy()

joined = gpd.sjoin(
    fields,
    irrigation_join,
    how='left',
    predicate='intersects',
)

# index_right is the index of the matched irrigation zone
# If a field intersects multiple zones, there will be DUPLICATE ROWS for that field
print(f"Rows in joined result: {len(joined)}")
print(f"Fields in input:       {len(fields)}")
dup_count = len(joined) - len(joined['field_id'].unique())
print(f"Duplicate rows (fields touching multiple zones): {dup_count}")
print()

# Show the join result
display_cols = ['field_id', 'crop_type', 'area_ha', 'zone_id', 'zone_name', 'water_source']
display_cols = [c for c in display_cols if c in joined.columns]
print("Join result (first 12 rows):")
print(joined[display_cols].to_string())

# ---------------------------------------------------------------------------
# STEP 4: Handle multi-zone fields — compute overlap percentages
# ---------------------------------------------------------------------------
print_section("STEP 4: Overlap Percentage Calculation (Multi-Zone Fields)")

print("""
Some fields intersect multiple irrigation districts.
For water billing and compliance, we need:
  - What percentage of each field falls in each district?
  - Which district "owns" the majority of the field?
This requires computing the INTERSECTION geometry and its area.
""")

# Reproject to UTM for accurate area calculations
fields_utm     = fields.to_crs("EPSG:32610")
irrigation_utm = irrigation.to_crs("EPSG:32610")

# Compute field areas in UTM
fields_utm['area_utm_m2'] = fields_utm.geometry.area

# For each (field, irrigation_zone) pair, compute the intersection area
overlap_records = []

for _, field_row in fields_utm.iterrows():
    field_area = field_row.geometry.area
    field_intersections = []

    for _, zone_row in irrigation_utm.iterrows():
        if field_row.geometry.intersects(zone_row.geometry):
            intersection_geom = field_row.geometry.intersection(zone_row.geometry)
            intersection_area = intersection_geom.area

            if intersection_area > 0.01:  # ignore trivial overlaps (< 0.01 m²)
                overlap_pct = (intersection_area / field_area) * 100

                field_intersections.append({
                    'field_id':         field_row['field_id'],
                    'crop_type':        field_row['crop_type'],
                    'field_area_m2':    field_area,
                    'zone_id':          zone_row['zone_id'],
                    'zone_name':        zone_row['zone_name'],
                    'water_source':     zone_row['water_source'],
                    'district_code':    zone_row['district_code'],
                    'annual_alloc_af':  zone_row['annual_allocation_af'],
                    'overlap_area_m2':  intersection_area,
                    'overlap_area_ha':  intersection_area / 10_000,
                    'overlap_pct':      round(overlap_pct, 2),
                    'is_primary_zone':  False,  # will set below
                })

    # Mark the zone with the largest overlap as the primary zone
    if field_intersections:
        primary_idx = max(range(len(field_intersections)),
                          key=lambda i: field_intersections[i]['overlap_pct'])
        field_intersections[primary_idx]['is_primary_zone'] = True
        overlap_records.extend(field_intersections)
    else:
        # Field has no irrigation zone assignment
        overlap_records.append({
            'field_id':         field_row['field_id'],
            'crop_type':        field_row['crop_type'],
            'field_area_m2':    field_area,
            'zone_id':          None,
            'zone_name':        'UNASSIGNED',
            'water_source':     None,
            'district_code':    None,
            'annual_alloc_af':  None,
            'overlap_area_m2':  0,
            'overlap_area_ha':  0,
            'overlap_pct':      0,
            'is_primary_zone':  False,
        })

overlap_df = pd.DataFrame(overlap_records)

print("Field-to-irrigation-zone overlap matrix:")
print(f"{'Field':>8} {'Zone':>10} {'Overlap%':>10} {'Primary':>8} {'Water Source':>20}")
print("-" * 65)
for _, row in overlap_df.iterrows():
    zone_id  = row['zone_id'] or 'NONE'
    primary  = "YES" if row['is_primary_zone'] else "no"
    source   = (row['water_source'] or 'n/a')[:20]
    print(f"{row['field_id']:>8} {zone_id:>10} {row['overlap_pct']:>9.1f}%  "
          f"{primary:>8}  {source:>20}")

# ---------------------------------------------------------------------------
# STEP 5: Identify multi-zone fields
# ---------------------------------------------------------------------------
print_section("STEP 5: Multi-Zone Field Analysis")

# Count number of zones each field is in
zone_count = overlap_df[overlap_df['zone_id'].notna()].groupby('field_id')['zone_id'].count()
multi_zone_fields = zone_count[zone_count > 1]

print(f"Fields with single irrigation zone: {(zone_count == 1).sum()}")
print(f"Fields with multiple irrigation zones: {len(multi_zone_fields)}")
print(f"Fields with NO irrigation zone: {(overlap_df['zone_id'].isna()).sum()}")

if len(multi_zone_fields) > 0:
    print(f"\nMulti-zone fields requiring special billing treatment:")
    for fid in multi_zone_fields.index:
        fid_rows = overlap_df[overlap_df['field_id'] == fid]
        print(f"\n  {fid}:")
        for _, row in fid_rows.iterrows():
            print(f"    {row['zone_id']}: {row['overlap_pct']:.1f}% "
                  f"({row['overlap_area_ha']:.2f} ha) — {row['water_source']}")
else:
    print("  No multi-zone fields found in this dataset.")

# ---------------------------------------------------------------------------
# STEP 6: Create enriched GeoDataFrame with primary zone attributes
# ---------------------------------------------------------------------------
print_section("STEP 6: Build Enriched GeoDataFrame")

# Select only primary zone records to avoid duplicating field rows
primary_assignments = overlap_df[
    (overlap_df['is_primary_zone'] == True) | (overlap_df['zone_id'].isna())
].copy()

# Merge back with original fields GeoDataFrame to keep the geometry
enriched = fields.merge(
    primary_assignments[['field_id', 'zone_id', 'zone_name', 'water_source',
                          'district_code', 'annual_alloc_af', 'overlap_pct']],
    on='field_id',
    how='left',
)

print(f"Enriched GeoDataFrame shape: {enriched.shape}")
print("New columns added from spatial join:")
print("  zone_id            → primary irrigation district ID")
print("  zone_name          → district full name")
print("  water_source       → Kings River / San Joaquin River / Federal")
print("  district_code      → short district code")
print("  annual_alloc_af    → annual water allocation in acre-feet")
print("  overlap_pct        → % of field area in primary district")

print()
print("Enriched fields (key columns):")
display = ['field_id', 'crop_type', 'area_ha', 'zone_id', 'water_source', 'overlap_pct']
display = [c for c in display if c in enriched.columns]
print(enriched[display].to_string())

# ---------------------------------------------------------------------------
# STEP 7: Export enriched GeoJSON
# ---------------------------------------------------------------------------
print_section("STEP 7: Export Enriched GeoJSON")

# Ensure we're in WGS84 before writing GeoJSON (RFC 7946 requirement)
enriched_wgs84 = enriched.to_crs("EPSG:4326") if enriched.crs != gpd.GeoSeries().crs else enriched

# Fill NaN strings for JSON serialization (JSON doesn't have NaN)
for col in ['zone_id', 'zone_name', 'water_source', 'district_code']:
    if col in enriched_wgs84.columns:
        enriched_wgs84[col] = enriched_wgs84[col].fillna("UNASSIGNED")

# Export
enriched_wgs84.to_file(OUTPUT_PATH, driver='GeoJSON')

file_size_kb = os.path.getsize(OUTPUT_PATH) / 1024
print(f"Exported: {OUTPUT_PATH}")
print(f"Features: {len(enriched_wgs84)}")
print(f"File size: {file_size_kb:.1f} KB")
print(f"Columns: {list(enriched_wgs84.columns)}")

# Verify by reloading
reloaded = gpd.read_file(OUTPUT_PATH)
print(f"\nVerification reload: {len(reloaded)} features, CRS={reloaded.crs}")
print("First 3 rows of enriched data:")
print(reloaded[['field_id', 'crop_type', 'zone_name', 'water_source', 'overlap_pct']].head(3).to_string())

# ---------------------------------------------------------------------------
# STEP 8: Summary statistics using spatial join results
# ---------------------------------------------------------------------------
print_section("STEP 8: Agricultural Summary by Water Source")

print("Area summary by irrigation water source:")
summary = (
    enriched
    .groupby('water_source')
    .agg(
        n_fields    = ('field_id', 'count'),
        total_ha    = ('area_ha', 'sum'),
        crops       = ('crop_type', lambda x: ', '.join(sorted(set(x)))),
    )
    .round(1)
)
print(summary.to_string())

print()
print("This spatial join result enables downstream analytics:")
print("  - Water usage per district (sum area_ha × irrigation coefficient per district)")
print("  - Crop mix by water district (for agricultural reporting)")
print("  - Fields at risk if a specific water source is curtailed (drought planning)")
print("  - Multi-district billing splits for straddling parcels")

print_section("Script Complete")
print("Key patterns demonstrated:")
print("  1. Load two GeoJSON layers into GeoDataFrames")
print("  2. Verify CRS match before spatial join")
print("  3. gpd.sjoin() for quick left-join overlap query")
print("  4. Manual intersection loop for overlap percentage calculation")
print("  5. Identify multi-zone fields for special handling")
print("  6. Merge spatial join results back to original GDF")
print("  7. Export enriched GeoJSON with joined attributes")
