"""
generate_readme_images.py - Repo 03: GeoJSON Processing and Visualization
Generates illustrative images using only matplotlib + numpy.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
import os

os.makedirs("images", exist_ok=True)

BG = "#f8f9fa"
DARK = "#212121"
BLUE = "#1565C0"
LIGHT_BLUE = "#90CAF9"
GREEN = "#2E7D32"
LIGHT_GREEN = "#C8E6C9"
RED = "#B71C1C"
ORANGE = "#E65100"
YELLOW_BG = "#FFF9C4"
PURPLE = "#4A148C"


# =============================================================
# IMAGE 1: geojson_structure.png
# GeoJSON specification anatomy diagram
# =============================================================
fig, ax = plt.subplots(figsize=(14, 9))
ax.set_xlim(0, 14)
ax.set_ylim(0, 9)
ax.axis('off')
fig.patch.set_facecolor("#1E1E2E")
ax.set_facecolor("#1E1E2E")

fig.suptitle("GeoJSON FeatureCollection — Structure Anatomy",
             fontsize=15, fontweight='bold', color='white', y=0.97)

# JSON code panel (left)
code_lines = [
    ("{",                         "#E2E8F0"),
    ('  "type": "FeatureCollection",', "#94C97A"),
    ('  "features": [',          "#E2E8F0"),
    ('    {',                    "#E2E8F0"),
    ('      "type": "Feature",', "#94C97A"),
    ('      "geometry": {',      "#E2E8F0"),
    ('        "type": "Polygon",', "#FF9E80"),
    ('        "coordinates": [', "#E2E8F0"),
    ('          [[-119.70, 36.70],', "#82B1FF"),
    ('           [-119.65, 36.70],', "#82B1FF"),
    ('           [-119.65, 36.75],', "#82B1FF"),
    ('           [-119.70, 36.75],', "#82B1FF"),
    ('           [-119.70, 36.70]]', "#82B1FF"),
    ('        ]',                 "#E2E8F0"),
    ('      },',                  "#E2E8F0"),
    ('      "properties": {',    "#E2E8F0"),
    ('        "field_id": "FF-001",', "#FFD54F"),
    ('        "crop_type": "corn",', "#FFD54F"),
    ('        "area_ha": 12.5',  "#FFD54F"),
    ('      }',                   "#E2E8F0"),
    ('    }',                     "#E2E8F0"),
    ('  ]',                       "#E2E8F0"),
    ('}',                         "#E2E8F0"),
]

for i, (line, color) in enumerate(code_lines):
    ax.text(0.3, 8.5 - i * 0.35, line, fontsize=8.2, color=color,
            fontfamily='monospace', va='top')

# Right panel: annotation callouts
callout_data = [
    (7.5, 8.2, "Root object type:\nFeatureCollection", "#94C97A"),
    (7.5, 6.9, "Geometry object:\ntype + coordinates", "#FF9E80"),
    (7.5, 5.5, "Coordinate array:\n[longitude, latitude]", "#82B1FF"),
    (7.5, 3.9, "RFC 7946: Always WGS84\nOrder: [lon, lat] NOT [lat, lon]", "#FF8A80"),
    (7.5, 2.7, "Properties: arbitrary\nJSON key-value pairs", "#FFD54F"),
]

for (cx, cy, txt, clr) in callout_data:
    box = FancyBboxPatch((cx - 0.15, cy - 0.55), 5.8, 0.75,
                         boxstyle="round,pad=0.1",
                         facecolor="#2D2D4E", edgecolor=clr,
                         linewidth=1.5, zorder=3)
    ax.add_patch(box)
    ax.text(cx + 2.75, cy - 0.1, txt, fontsize=8.5, color=clr,
            ha='center', va='center', fontweight='bold', zorder=4)

# Geometry type mini-icons (bottom strip)
geo_types = [
    ("Point", 1.2, 1.2),
    ("LineString", 3.5, 1.2),
    ("Polygon", 5.8, 1.2),
    ("MultiPolygon", 8.5, 1.2),
    ("GeomCollection", 11.2, 1.2),
]

colors_gt = ["#EF5350", "#42A5F5", "#66BB6A", "#FFA726", "#AB47BC"]
for (lbl, gx, gy), gc in zip(geo_types, colors_gt):
    circle = plt.Circle((gx, gy), 0.38, color=gc, alpha=0.85, zorder=4)
    ax.add_patch(circle)
    ax.text(gx, gy - 0.7, lbl, ha='center', va='top', fontsize=7.5,
            color='white', fontweight='bold', zorder=5)

ax.text(7.0, 0.15, "GeoJSON supports 6 geometry types  |  Always WGS84 (EPSG:4326)  |  [lon, lat] coordinate order",
        ha='center', fontsize=8, color='#90A4AE', style='italic')

fig.tight_layout()
fig.savefig("images/geojson_structure.png", dpi=150, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close(fig)
print("Saved: images/geojson_structure.png")


# =============================================================
# IMAGE 2: geojson_format_comparison.png
# GeoJSON vs Shapefile vs GeoPackage comparison
# =============================================================
fig, axes = plt.subplots(1, 3, figsize=(15, 8))
fig.patch.set_facecolor(BG)
fig.suptitle("Geospatial Vector Format Comparison", fontsize=15,
             fontweight='bold', color=DARK, y=0.98)

formats = [
    {
        "name": "GeoJSON",
        "ext": ".geojson",
        "color": "#1565C0",
        "bg": "#E3F2FD",
        "icon_color": "#1976D2",
        "traits": [
            ("Human readable", True),
            ("Single file", True),
            ("Web-native", True),
            ("Large file support", False),
            ("Multiple layers", False),
            ("Binary efficiency", False),
            ("Always WGS84", True),
            ("Index support", False),
        ],
        "size_factor": 1.0,
        "use_cases": ["Web APIs", "Leaflet/Mapbox", "GitHub rendering", "Simple exchange"],
    },
    {
        "name": "Shapefile",
        "ext": ".shp + sidecar",
        "color": "#1B5E20",
        "bg": "#E8F5E9",
        "icon_color": "#2E7D32",
        "traits": [
            ("Human readable", False),
            ("Single file", False),
            ("Web-native", False),
            ("Large file support", True),
            ("Multiple layers", False),
            ("Binary efficiency", True),
            ("Always WGS84", False),
            ("Index support", True),
        ],
        "size_factor": 0.35,
        "use_cases": ["GIS software", "USDA/agency data", "Legacy pipelines", "Field instruments"],
    },
    {
        "name": "GeoPackage",
        "ext": ".gpkg",
        "color": "#4A148C",
        "bg": "#F3E5F5",
        "icon_color": "#6A1B9A",
        "traits": [
            ("Human readable", False),
            ("Single file", True),
            ("Web-native", False),
            ("Large file support", True),
            ("Multiple layers", True),
            ("Binary efficiency", True),
            ("Always WGS84", False),
            ("Index support", True),
        ],
        "size_factor": 0.25,
        "use_cases": ["Mobile/offline GIS", "Multi-layer projects", "SQLite inspection", "Open standard"],
    },
]

for ax, fmt in zip(axes, formats):
    ax.set_facecolor(fmt["bg"])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')

    # Header
    header = FancyBboxPatch((0, 10.5), 10, 1.4,
                             boxstyle="round,pad=0.1",
                             facecolor=fmt["color"], edgecolor='none', zorder=2)
    ax.add_patch(header)
    ax.text(5, 11.25, fmt["name"], ha='center', va='center',
            fontsize=16, fontweight='bold', color='white', zorder=3)
    ax.text(5, 10.7, fmt["ext"], ha='center', va='center',
            fontsize=9, color='#BBDEFB', zorder=3)

    # Traits checklist
    for i, (trait, supported) in enumerate(fmt["traits"]):
        y = 9.8 - i * 0.9
        symbol = "✓" if supported else "✗"
        color = "#2E7D32" if supported else "#B71C1C"
        bg_c = "#C8E6C9" if supported else "#FFCDD2"
        box = FancyBboxPatch((0.3, y - 0.3), 9.4, 0.65,
                              boxstyle="round,pad=0.05",
                              facecolor=bg_c, edgecolor='none', alpha=0.7, zorder=2)
        ax.add_patch(box)
        ax.text(1.2, y + 0.02, symbol, ha='center', va='center',
                fontsize=13, color=color, fontweight='bold', zorder=3)
        ax.text(2.0, y + 0.02, trait, ha='left', va='center',
                fontsize=9, color=DARK, zorder=3)

    # File size bar
    ax.text(5, 1.95, "Relative file size", ha='center', fontsize=8.5,
            color='#555', style='italic')
    bar = FancyBboxPatch((0.5, 1.3), 9 * fmt["size_factor"], 0.5,
                          boxstyle="round,pad=0.05",
                          facecolor=fmt["icon_color"], edgecolor='none',
                          alpha=0.8, zorder=2)
    ax.add_patch(bar)
    ax.text(0.5 + 9 * fmt["size_factor"] / 2, 1.55,
            f'{int(fmt["size_factor"] * 100)}%',
            ha='center', va='center', fontsize=9, color='white',
            fontweight='bold', zorder=3)

    # Use cases
    ax.text(5, 0.9, "Best for:", ha='center', fontsize=8, color='#555',
            fontweight='bold')
    uc_text = " | ".join(fmt["use_cases"])
    ax.text(5, 0.45, uc_text, ha='center', fontsize=7, color=fmt["color"],
            wrap=True)

    ax.set_title(fmt["name"], fontsize=13, fontweight='bold',
                 color=fmt["color"], pad=10)

fig.tight_layout(pad=2)
fig.savefig("images/geojson_format_comparison.png", dpi=150, bbox_inches='tight')
plt.close(fig)
print("Saved: images/geojson_format_comparison.png")


# =============================================================
# IMAGE 3: geojson_farm_fields.png
# Simulated farm field polygons coloured by crop type
# =============================================================
fig, axes = plt.subplots(1, 2, figsize=(14, 7))
fig.patch.set_facecolor(BG)
fig.suptitle("Farm Field GeoJSON — Spatial Queries & Attribute Filtering",
             fontsize=14, fontweight='bold', color=DARK, y=0.98)

np.random.seed(42)

# Simulated field polygons (grid-like, realistic farm shapes)
fields = [
    # (x, y, w, h, crop, area_ha, ndvi)
    (0.05, 0.55, 0.28, 0.38, "corn",     42.1, 0.72),
    (0.36, 0.55, 0.22, 0.38, "wheat",    31.5, 0.65),
    (0.61, 0.55, 0.32, 0.38, "soybean",  45.8, 0.68),
    (0.05, 0.08, 0.20, 0.42, "corn",     28.7, 0.75),
    (0.28, 0.20, 0.30, 0.30, "fallow",   19.2, 0.18),
    (0.61, 0.08, 0.15, 0.42, "wheat",    21.4, 0.61),
    (0.79, 0.08, 0.14, 0.42, "soybean",  18.9, 0.70),
    (0.28, 0.08, 0.30, 0.09, "road",      5.1, 0.05),
]

crop_colors = {
    "corn": "#FFD600",
    "wheat": "#FF8F00",
    "soybean": "#43A047",
    "fallow": "#BDBDBD",
    "road": "#607D8B",
}

# LEFT: Crop type map
ax = axes[0]
ax.set_facecolor("#D7ECD9")
ax.set_title("Crop Type Map (by field attribute)", fontsize=11,
             fontweight='bold', color=DARK, pad=8)

for (x, y, w, h, crop, area, ndvi) in fields:
    poly = FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0",
                           facecolor=crop_colors[crop], edgecolor='white',
                           linewidth=2, alpha=0.88, zorder=2)
    ax.add_patch(poly)
    ax.text(x + w / 2, y + h / 2, f"{crop}\n{area:.0f} ha",
            ha='center', va='center', fontsize=8, fontweight='bold',
            color='#212121' if crop != 'road' else 'white', zorder=3)

ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax.set_xlabel("Longitude (relative)", fontsize=9)
ax.set_ylabel("Latitude (relative)", fontsize=9)
ax.grid(True, linestyle='--', alpha=0.3, color='white')

legend_handles = [mpatches.Patch(facecolor=c, label=k.capitalize(), edgecolor='gray')
                  for k, c in crop_colors.items()]
ax.legend(handles=legend_handles, loc='lower right', fontsize=8,
          title='Crop Type', title_fontsize=9, framealpha=0.9)

# RIGHT: NDVI choropleth
ax = axes[1]
ax.set_facecolor("#D7ECD9")
ax.set_title("NDVI Choropleth (spatial query: NDVI > 0.60 highlighted)",
             fontsize=11, fontweight='bold', color=DARK, pad=8)

import matplotlib.cm as cm
ndvi_cmap = cm.RdYlGn

for (x, y, w, h, crop, area, ndvi) in fields:
    facecolor = ndvi_cmap(ndvi)
    poly = FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0",
                           facecolor=facecolor, edgecolor='white',
                           linewidth=2, alpha=0.9, zorder=2)
    ax.add_patch(poly)
    ax.text(x + w / 2, y + h / 2, f"NDVI\n{ndvi:.2f}",
            ha='center', va='center', fontsize=8.5, fontweight='bold',
            color='#212121' if ndvi > 0.4 else 'white', zorder=3)
    # Highlight high NDVI
    if ndvi > 0.60:
        highlight = FancyBboxPatch((x - 0.01, y - 0.01), w + 0.02, h + 0.02,
                                    boxstyle="square,pad=0",
                                    facecolor='none', edgecolor='#1565C0',
                                    linewidth=3, zorder=4)
        ax.add_patch(highlight)

ax.set_xlim(0, 1); ax.set_ylim(0, 1)
ax.set_xlabel("Longitude (relative)", fontsize=9)
ax.set_ylabel("Latitude (relative)", fontsize=9)
ax.grid(True, linestyle='--', alpha=0.3, color='white')

sm = plt.cm.ScalarMappable(cmap=ndvi_cmap, norm=plt.Normalize(0, 1))
sm.set_array([])
cbar = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.02)
cbar.set_label("NDVI", fontsize=9)
cbar.ax.tick_params(labelsize=8)

# Blue border legend
ax.plot([], [], color='#1565C0', linewidth=3, label='NDVI > 0.60 (high vigour)')
ax.legend(loc='lower right', fontsize=8.5, framealpha=0.9)

fig.tight_layout(pad=2)
fig.savefig("images/geojson_farm_fields.png", dpi=150, bbox_inches='tight')
plt.close(fig)
print("Saved: images/geojson_farm_fields.png")


print("\nAll images generated in images/")
