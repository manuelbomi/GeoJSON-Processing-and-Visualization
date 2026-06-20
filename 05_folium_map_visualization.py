"""
05_folium_map_visualization.py
================================
Author: Emmanuel Oyekanlu — Principal Data Engineer

PURPOSE:
    Create a production-quality interactive web map using Folium that displays:
      1. A choropleth layer of farm fields colored by area_ha
      2. Irrigation district overlay with distinct styling
      3. Clickable popups with full field attribute tables
      4. Hover tooltips showing field ID and crop type
      5. Layer control to toggle field and irrigation layers
      6. A legend explaining the color scale
    Saves the result as a self-contained HTML file.

REAL-WORLD CONTEXT:
    Interactive maps are critical for:
      - Farm management dashboards: field operators view zone assignments on tablets
      - Stakeholder reports: executive presentations with clickable maps
      - Public-facing web portals: irrigation district water usage maps
      - AGV fleet monitoring: real-time position map in operations center
      - Data quality review: geospatial data engineers spot anomalies visually

    Folium generates Leaflet.js HTML — the output is a single .html file that
    works in any browser with no server required. It can be:
      - Emailed as an attachment
      - Served from S3 as a static website
      - Embedded in a Jupyter notebook
      - Included in a PDF report (via headless browser screenshot)

DEPENDENCIES:
    folium, branca, geopandas, json

USAGE:
    python 05_folium_map_visualization.py
    # Then open map_visualization.html in your browser

OUTPUT:
    map_visualization.html — interactive Leaflet.js map
"""

import os
import json
import geopandas as gpd
import folium
from folium import GeoJson, GeoJsonTooltip, GeoJsonPopup
from folium.plugins import FloatImage
import branca
import branca.colormap as cm

SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
FIELDS_PATH     = os.path.join(SCRIPT_DIR, "data", "farm_fields.geojson")
IRRIGATION_PATH = os.path.join(SCRIPT_DIR, "data", "irrigation_zones.geojson")
OUTPUT_PATH     = os.path.join(SCRIPT_DIR, "map_visualization.html")


def print_section(title: str) -> None:
    width = 65
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


# ---------------------------------------------------------------------------
# STEP 1: Load and prepare data
# ---------------------------------------------------------------------------
print_section("STEP 1: Load and Prepare Data")

fields     = gpd.read_file(FIELDS_PATH)
irrigation = gpd.read_file(IRRIGATION_PATH)

# Compute accurate area using UTM projection
fields_utm = fields.to_crs("EPSG:32610")
fields['area_ha_computed'] = fields_utm.geometry.area / 10_000

print(f"Fields loaded:      {len(fields)} features")
print(f"Area range:         {fields['area_ha_computed'].min():.1f} - {fields['area_ha_computed'].max():.1f} ha")
print(f"Irrigation zones:   {len(irrigation)} features")

# Center the map on the mean centroid of the field dataset
map_center_lat = fields.geometry.centroid.y.mean()
map_center_lon = fields.geometry.centroid.x.mean()
print(f"Map center:         lat={map_center_lat:.4f}, lon={map_center_lon:.4f}")

# Convert GeoDataFrames to GeoJSON dicts for Folium (in WGS84)
fields_geojson     = json.loads(fields.to_json())
irrigation_geojson = json.loads(irrigation.to_json())

# ---------------------------------------------------------------------------
# STEP 2: Define color scales
# ---------------------------------------------------------------------------
print_section("STEP 2: Color Scales and Style Functions")

# Choropleth color scale for area_ha (continuous)
# branca.colormap provides LinearColormap — a continuous color gradient
area_min = fields['area_ha_computed'].min()
area_max = fields['area_ha_computed'].max()

area_colormap = cm.LinearColormap(
    colors=['#FFFDE7', '#FFF176', '#FFCA28', '#FF8F00', '#E65100'],
    # Pale yellow → Yellow → Amber → Orange → Dark orange
    vmin=area_min,
    vmax=area_max,
    caption='Field Area (hectares)',
)

# Crop type → color mapping (for tooltip styling)
crop_colors = {
    "corn":    "#4CAF50",   # green
    "wheat":   "#FFC107",   # amber
    "soy":     "#8BC34A",   # light green
    "alfalfa": "#2196F3",   # blue
}

# Style function for the choropleth layer
# This is a Python lambda that Folium calls for each GeoJSON Feature.
# It returns a dict with Leaflet PathOptions (fillColor, color, etc.)
def field_style_function(feature):
    """
    Compute fill color for each field based on its area_ha_computed attribute.
    Called by Folium's GeoJson layer for each feature during map rendering.
    """
    area = feature['properties'].get('area_ha_computed', 0)
    if area is None:
        area = 0
    return {
        'fillColor':   area_colormap(area),
        'color':       '#333333',      # polygon border color
        'weight':      1.5,            # border width in pixels
        'fillOpacity': 0.75,           # fill transparency
        'opacity':     1.0,            # border opacity
    }

def field_highlight_function(feature):
    """Style applied when mouse hovers over a field polygon."""
    return {
        'fillColor':   '#FFD54F',     # bright highlight color on hover
        'color':       '#E65100',     # orange border on hover
        'weight':      3.0,
        'fillOpacity': 0.85,
    }

def irrigation_style_function(feature):
    """Style for irrigation district polygons — semi-transparent blue overlay."""
    # Use different shades for different districts
    zone_colors = {
        "IRZ-001": "#1565C0",
        "IRZ-002": "#0D47A1",
        "IRZ-003": "#283593",
    }
    zone_id = feature['properties'].get('zone_id', 'IRZ-001')
    return {
        'fillColor':   zone_colors.get(zone_id, '#1565C0'),
        'color':       '#0D47A1',
        'weight':      2.5,
        'fillOpacity': 0.15,   # very transparent — shows field colors underneath
        'opacity':     0.8,
        'dashArray':   '6 4',  # dashed border to distinguish from field borders
    }

# ---------------------------------------------------------------------------
# STEP 3: Build the Folium map
# ---------------------------------------------------------------------------
print_section("STEP 3: Build Folium Map")

# Initialize the base map
# location: [latitude, longitude] — note: Folium uses lat/lon order
# zoom_start: initial zoom level (1=world, 18=building)
# tiles: base map provider
m = folium.Map(
    location=[map_center_lat, map_center_lon],
    zoom_start=12,
    tiles='CartoDB positron',    # Clean, light gray base map — good for data overlays
    prefer_canvas=True,          # Use Canvas renderer for better performance with many polygons
)

# Add OpenStreetMap as an alternative tile layer
folium.TileLayer(
    tiles='OpenStreetMap',
    name='OpenStreetMap',
    control=True,
).add_to(m)

folium.TileLayer(
    tiles='CartoDB dark_matter',
    name='Dark Mode',
    control=True,
).add_to(m)

print("Base map initialized")
print(f"  Center: {map_center_lat:.4f}, {map_center_lon:.4f}")
print(f"  Default zoom: 12")
print(f"  Tile layers: CartoDB positron, OpenStreetMap, CartoDB dark_matter")

# ---------------------------------------------------------------------------
# STEP 4: Add irrigation district layer
# ---------------------------------------------------------------------------
print_section("STEP 4: Add Irrigation Districts Layer")

# Tooltip for irrigation districts (shows on hover)
irr_tooltip = GeoJsonTooltip(
    fields=['zone_name', 'water_source', 'district_code', 'annual_allocation_af'],
    aliases=['District:', 'Water Source:', 'Code:', 'Annual Alloc. (AF):'],
    localize=True,
    sticky=False,
    style=(
        "background-color: #1565C0; color: white; font-family: Arial; "
        "font-size: 12px; padding: 8px; border-radius: 4px;"
    ),
)

# Popup for irrigation districts (shows on click)
irr_popup = GeoJsonPopup(
    fields=['zone_name', 'water_source', 'district_code',
            'annual_allocation_af', 'delivery_method', 'established_year'],
    aliases=['District Name:', 'Water Source:', 'District Code:',
             'Annual Allocation (AF):', 'Delivery Method:', 'Established:'],
    localize=True,
    max_width=350,
    style="font-family: Arial; font-size: 13px;",
)

irr_layer = GeoJson(
    irrigation_geojson,
    name="Irrigation Districts",        # name shown in LayerControl
    style_function=irrigation_style_function,
    tooltip=irr_tooltip,
    popup=irr_popup,
    show=True,                          # visible by default
).add_to(m)

print(f"Irrigation districts layer added ({len(irrigation)} zones)")

# ---------------------------------------------------------------------------
# STEP 5: Add farm fields choropleth layer
# ---------------------------------------------------------------------------
print_section("STEP 5: Add Farm Fields Choropleth Layer")

# Tooltip: shown on hover — keep brief
field_tooltip = GeoJsonTooltip(
    fields=['field_id', 'crop_type', 'area_ha_computed'],
    aliases=['Field:', 'Crop:', 'Area (ha):'],
    localize=True,
    sticky=True,     # tooltip follows mouse movement
    style=(
        "background-color: #263238; color: white; font-family: Arial; "
        "font-size: 12px; padding: 8px; border-radius: 4px; "
        "box-shadow: 2px 2px 4px rgba(0,0,0,0.4);"
    ),
    labels=True,
)

# Popup: shown on click — can be more detailed
popup_html_template = """
<div style="font-family: Arial; font-size: 13px; min-width: 250px;">
  <div style="background: #1A237E; color: white; padding: 8px 12px;
              border-radius: 4px 4px 0 0; font-weight: bold; font-size: 14px;">
    Field: {field_id}
  </div>
  <table style="width: 100%; border-collapse: collapse; margin-top: 0;">
    <tr style="background: #E3F2FD;">
      <td style="padding: 5px 10px; color: #555;">Crop Type</td>
      <td style="padding: 5px 10px; font-weight: bold;">{crop_type}</td>
    </tr>
    <tr>
      <td style="padding: 5px 10px; color: #555;">Area</td>
      <td style="padding: 5px 10px;">{area_ha_computed:.2f} ha</td>
    </tr>
    <tr style="background: #E3F2FD;">
      <td style="padding: 5px 10px; color: #555;">Irrigation</td>
      <td style="padding: 5px 10px;">{irrigation_type}</td>
    </tr>
    <tr>
      <td style="padding: 5px 10px; color: #555;">Farmer</td>
      <td style="padding: 5px 10px;">{farmer}</td>
    </tr>
    <tr style="background: #E3F2FD;">
      <td style="padding: 5px 10px; color: #555;">Soil Type</td>
      <td style="padding: 5px 10px;">{soil_type}</td>
    </tr>
    <tr>
      <td style="padding: 5px 10px; color: #555;">Yield</td>
      <td style="padding: 5px 10px;">{yield_t_ha} t/ha</td>
    </tr>
    <tr style="background: #E3F2FD;">
      <td style="padding: 5px 10px; color: #555;">Planting Date</td>
      <td style="padding: 5px 10px;">{planting_date}</td>
    </tr>
    <tr>
      <td style="padding: 5px 10px; color: #555;">Harvest Date</td>
      <td style="padding: 5px 10px;">{harvest_date}</td>
    </tr>
  </table>
</div>
"""

# Add the GeoJson layer with style + highlight + tooltip + popup
field_layer = GeoJson(
    fields_geojson,
    name="Farm Fields (choropleth: area ha)",
    style_function=field_style_function,
    highlight_function=field_highlight_function,
    tooltip=field_tooltip,
    # Build per-feature popups using GeoJsonPopup
    popup=GeoJsonPopup(
        fields=['field_id', 'crop_type', 'area_ha_computed', 'irrigation_type',
                'farmer', 'soil_type', 'yield_t_ha', 'planting_date', 'harvest_date'],
        aliases=['Field ID:', 'Crop Type:', 'Area (ha):', 'Irrigation:',
                 'Farmer:', 'Soil Type:', 'Yield (t/ha):', 'Planting:', 'Harvest:'],
        localize=True,
        max_width=400,
        style="font-family: Arial; font-size: 13px;",
    ),
    show=True,
).add_to(m)

print(f"Farm fields choropleth layer added ({len(fields)} fields)")

# ---------------------------------------------------------------------------
# STEP 6: Add the colormap legend
# ---------------------------------------------------------------------------
print_section("STEP 6: Add Colormap Legend")

# Add the branca colormap as a legend on the map
area_colormap.add_to(m)

print("Choropleth legend added: area_ha scale (yellow → orange)")

# ---------------------------------------------------------------------------
# STEP 7: Add centroid markers with crop type coloring
# ---------------------------------------------------------------------------
print_section("STEP 7: Add Field Centroid Markers")

# Add a FeatureGroup so markers can be toggled independently
centroid_group = folium.FeatureGroup(name="Field Centroids (crop type)", show=False)

for _, row in fields.iterrows():
    cx = row.geometry.centroid.x
    cy = row.geometry.centroid.y

    crop = row['crop_type']
    color = {
        'corn':    'green',
        'wheat':   'orange',
        'soy':     'lightgreen',
        'alfalfa': 'blue',
    }.get(crop, 'gray')

    marker = folium.CircleMarker(
        location=[cy, cx],      # [lat, lon] for Folium
        radius=6,
        color='white',
        weight=1.5,
        fill=True,
        fill_color=color,
        fill_opacity=0.9,
        tooltip=f"{row['field_id']} — {crop.capitalize()}",
        popup=folium.Popup(
            f"<b>{row['field_id']}</b><br>Crop: {crop}<br>Area: {row['area_ha_computed']:.1f} ha",
            max_width=200,
        ),
    )
    marker.add_to(centroid_group)

centroid_group.add_to(m)
print(f"Added {len(fields)} centroid markers (toggle in layer control)")

# ---------------------------------------------------------------------------
# STEP 8: Add custom HTML legend for crop types
# ---------------------------------------------------------------------------
print_section("STEP 8: Add Custom HTML Legend")

legend_html = """
<div style="
    position: fixed;
    bottom: 60px;
    left: 15px;
    z-index: 1000;
    background-color: rgba(255, 255, 255, 0.92);
    padding: 14px 18px;
    border-radius: 8px;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.3);
    font-family: Arial, sans-serif;
    font-size: 13px;
    line-height: 1.8;
">
    <div style="font-weight: bold; font-size: 14px; margin-bottom: 8px;
                color: #1A237E; border-bottom: 2px solid #1A237E; padding-bottom: 4px;">
        Crop Types
    </div>
    <div><span style="display:inline-block; width:14px; height:14px;
                       background:#4CAF50; border-radius:50%; margin-right:8px;"></span>Corn</div>
    <div><span style="display:inline-block; width:14px; height:14px;
                       background:#FFC107; border-radius:50%; margin-right:8px;"></span>Wheat</div>
    <div><span style="display:inline-block; width:14px; height:14px;
                       background:#8BC34A; border-radius:50%; margin-right:8px;"></span>Soy</div>
    <div><span style="display:inline-block; width:14px; height:14px;
                       background:#2196F3; border-radius:50%; margin-right:8px;"></span>Alfalfa</div>
    <div style="margin-top: 10px; font-size: 11px; color: #666;">
        ● Field choropleth = area (ha)<br>
        ◯ Centroid dots = crop type<br>
        Dashed lines = irrigation districts
    </div>
    <div style="margin-top: 8px; font-size: 10px; color: #999;">
        Data: Fresno Valley, CA (synthetic)
    </div>
</div>
"""

m.get_root().html.add_child(folium.Element(legend_html))
print("Custom crop type legend added (bottom-left)")

# ---------------------------------------------------------------------------
# STEP 9: Add title bar
# ---------------------------------------------------------------------------
title_html = """
<div style="
    position: fixed;
    top: 10px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1001;
    background-color: rgba(26, 35, 126, 0.92);
    color: white;
    padding: 10px 24px;
    border-radius: 8px;
    font-family: Arial, sans-serif;
    font-size: 16px;
    font-weight: bold;
    box-shadow: 2px 2px 8px rgba(0,0,0,0.4);
    text-align: center;
">
    Fresno Valley Agricultural Fields — Geospatial Analysis
    <div style="font-size: 11px; font-weight: normal; margin-top: 2px; color: #C5CAE9;">
        GeoPandas + Folium | Emmanuel Oyekanlu, Principal Data Engineer
    </div>
</div>
"""
m.get_root().html.add_child(folium.Element(title_html))

# ---------------------------------------------------------------------------
# STEP 10: Add layer control and save
# ---------------------------------------------------------------------------
print_section("STEP 10: Layer Control and Save")

# LayerControl adds a toggle widget (top-right corner by default)
# Allows users to show/hide individual layers
folium.LayerControl(
    position='topright',
    collapsed=False,       # expand the control panel by default
).add_to(m)

# Fit the map to the bounding box of the field data
# fitBounds expects [[south, west], [north, east]]
f_bounds = fields.total_bounds  # (minx, miny, maxx, maxy)
m.fit_bounds([
    [f_bounds[1], f_bounds[0]],   # [south, west]
    [f_bounds[3], f_bounds[2]],   # [north, east]
])

# Save the map
m.save(OUTPUT_PATH)
file_size_kb = os.path.getsize(OUTPUT_PATH) / 1024
print(f"Map saved: {OUTPUT_PATH}")
print(f"File size: {file_size_kb:.1f} KB  (self-contained HTML with Leaflet.js)")

print_section("Map Summary")
print(f"  Base maps:          CartoDB positron, OpenStreetMap, Dark Mode")
print(f"  Farm fields:        {len(fields)} polygons, choropleth by area (ha)")
print(f"  Irrigation zones:   {len(irrigation)} overlapping district polygons")
print(f"  Centroid markers:   {len(fields)} circle markers colored by crop type")
print(f"  Popups:             Click any field or district for full attribute table")
print(f"  Tooltips:           Hover over fields for quick info")
print(f"  Layer control:      Toggle all layers independently (top-right)")
print(f"  Legend:             Area colorscale + crop type legend")
print()
print(f"OPEN IN BROWSER:")
print(f"  Start Firefox/Chrome and navigate to:")
print(f"  {OUTPUT_PATH}")
print()
print("PRODUCTION USES:")
print("  - Serve this HTML from S3 as a static website")
print("  - Embed in a Jupyter notebook with IFrame(src='...', width=900, height=600)")
print("  - Screenshot with headless Chrome for PDF reports:")
print("    chromium --headless --screenshot=map.png map_visualization.html")
