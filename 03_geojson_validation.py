"""
03_geojson_validation.py
=========================
Author: Emmanuel Oyekanlu — Principal Data Engineer

PURPOSE:
    Implement a comprehensive GeoJSON validation pipeline that checks:
      1. Structural validity (required keys, type values, nesting)
      2. Coordinate validity (no NaN, no Infinity, correct nesting depth)
      3. Geometry validity (self-intersections, degenerate polygons)
      4. CRS compliance (GeoJSON must be WGS84)
      5. Domain-specific business rules (field areas, planting dates)
    And generates a formatted validation report.

REAL-WORLD CONTEXT:
    In any data pipeline that accepts user-uploaded GeoJSON:
      - Farm boundary uploads from a mobile app
      - Zone configuration files from a warehouse commissioning team
      - Environmental monitoring boundary files from a regulatory agency

    You CANNOT trust incoming GeoJSON to be well-formed. Common real-world errors:
      - Missing `geometry` key (null geometry features)
      - Coordinate order reversed: (lat, lon) instead of (lon, lat)
      - Unclosed polygon rings (first ≠ last coordinate)
      - Self-intersecting polygons (figure-8 shapes — invalid per OGC spec)
      - NaN coordinates from GPS glitches
      - Wrong nesting depth (flat list instead of list-of-list-of-list for Polygon)
      - Field properties with wrong types (area_ha as a string instead of float)
      - Non-WGS84 coordinates sneaked in as GeoJSON (EPSG:3857 values like 13,000,000)

    Catching these early (before PostGIS insert or Shapely processing) prevents
    cryptic downstream errors and data corruption.

USAGE:
    python 03_geojson_validation.py
"""

import os
import json
import math
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

# We use both geojson and shapely for different validation layers
try:
    import geojson
    HAS_GEOJSON = True
except ImportError:
    HAS_GEOJSON = False

from shapely.geometry import shape
from shapely.validation import explain_validity

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VALID_PATH  = os.path.join(SCRIPT_DIR, "data", "farm_fields.geojson")

# ---------------------------------------------------------------------------
# Validation Issue class
# ---------------------------------------------------------------------------

class ValidationIssue:
    """Represents a single validation finding."""
    SEVERITY_ERROR   = "ERROR"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_INFO    = "INFO"

    def __init__(self, severity: str, category: str, feature_id: Optional[str],
                 message: str, fix_suggestion: str = ""):
        self.severity       = severity
        self.category       = category
        self.feature_id     = feature_id    # None = applies to FeatureCollection
        self.message        = message
        self.fix_suggestion = fix_suggestion
        self.timestamp      = datetime.utcnow().isoformat()

    def __str__(self) -> str:
        fid = f"[{self.feature_id}]" if self.feature_id else "[collection]"
        return f"  {self.severity:<9} {self.category:<20} {fid:<12} {self.message}"


# ---------------------------------------------------------------------------
# GeoJSON Validator class
# ---------------------------------------------------------------------------

class GeoJSONValidator:
    """
    Multi-layer GeoJSON validator for production data ingestion pipelines.

    Validation layers (in order):
      1. JSON parse (if string input)
      2. FeatureCollection structure
      3. Per-Feature structure
      4. Geometry coordinate validity
      5. Shapely geometry validity (topology)
      6. WGS84 coordinate range check
      7. Business domain rules (configurable)
    """

    # WGS84 valid coordinate ranges
    LON_MIN, LON_MAX = -180.0, 180.0
    LAT_MIN, LAT_MAX =  -90.0,  90.0

    # Valid GeoJSON geometry type names
    VALID_GEOM_TYPES = {
        "Point", "MultiPoint", "LineString", "MultiLineString",
        "Polygon", "MultiPolygon", "GeometryCollection"
    }

    def __init__(self, domain_rules: Optional[Dict] = None):
        """
        Args:
            domain_rules: Optional dict of business constraints.
              Example: {
                'area_ha': {'min': 0.1, 'max': 5000},
                'crop_type': {'allowed': ['corn', 'wheat', 'soy', 'alfalfa']},
              }
        """
        self.domain_rules = domain_rules or {}
        self.issues: List[ValidationIssue] = []

    def _add(self, severity: str, category: str, feature_id: Optional[str],
             message: str, fix: str = "") -> None:
        self.issues.append(ValidationIssue(severity, category, feature_id, message, fix))

    def validate(self, data: Any) -> "GeoJSONValidator":
        """
        Run all validation layers against the input data.
        `data` can be a dict (already parsed) or a JSON string.
        Returns self for method chaining.
        """
        self.issues = []

        # Layer 1: JSON parsing
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                self._add("ERROR", "json_parse", None,
                          f"Invalid JSON: {e}",
                          "Fix syntax error in the JSON file")
                return self   # cannot continue without valid JSON

        # Layer 2: Top-level FeatureCollection structure
        self._validate_feature_collection(data)

        # Layer 3-7: Per-feature validation
        features = data.get("features", [])
        for i, feature in enumerate(features):
            fid = feature.get("id") or feature.get("properties", {}).get("field_id", f"index_{i}")
            self._validate_feature(feature, str(fid))

        return self

    def _validate_feature_collection(self, data: dict) -> None:
        """Layer 2: FeatureCollection-level checks."""

        # Must have 'type' key
        if 'type' not in data:
            self._add("ERROR", "structure", None,
                      "Missing required key 'type'",
                      "Add: \"type\": \"FeatureCollection\"")
            return

        if data['type'] != 'FeatureCollection':
            self._add("ERROR", "structure", None,
                      f"Top-level 'type' must be 'FeatureCollection', got '{data['type']}'",
                      "Change 'type' to 'FeatureCollection' or wrap in one")

        # Must have 'features' key
        if 'features' not in data:
            self._add("ERROR", "structure", None,
                      "Missing required key 'features'",
                      "Add: \"features\": [...]")
            return

        if not isinstance(data['features'], list):
            self._add("ERROR", "structure", None,
                      f"'features' must be an array, got {type(data['features']).__name__}",
                      "Wrap features in a JSON array: [...]")
            return

        # Empty collection is technically valid per spec but warn for data pipelines
        if len(data['features']) == 0:
            self._add("WARNING", "data_quality", None,
                      "FeatureCollection has 0 features",
                      "Check upload source — empty collections may indicate a failed export")

        # CRS field check (RFC 7946 deprecated explicit CRS member)
        if 'crs' in data:
            self._add("INFO", "crs", None,
                      "Explicit 'crs' member present — RFC 7946 deprecated this field",
                      "Remove 'crs' member; GeoJSON is implicitly WGS84")

        self._add("INFO", "structure", None,
                  f"FeatureCollection with {len(data.get('features', []))} features — structure OK")

    def _validate_feature(self, feature: dict, fid: str) -> None:
        """Layers 3-7: Per-feature validation."""

        # Layer 3a: Feature structure
        if not isinstance(feature, dict):
            self._add("ERROR", "structure", fid,
                      f"Feature is not an object (got {type(feature).__name__})",
                      "Each element of 'features' must be a JSON object")
            return

        if feature.get('type') != 'Feature':
            self._add("ERROR", "structure", fid,
                      f"Feature 'type' must be 'Feature', got '{feature.get('type')}'",
                      "Set \"type\": \"Feature\" on each feature object")

        if 'geometry' not in feature:
            self._add("ERROR", "structure", fid,
                      "Feature missing required 'geometry' key",
                      "Add a geometry object or null if geometry is intentionally absent")
            return

        if 'properties' not in feature:
            self._add("WARNING", "structure", fid,
                      "Feature missing 'properties' key",
                      "Add \"properties\": {} for features without attributes")

        # Layer 3b: Null geometry (allowed by spec but may indicate data loss)
        geom = feature['geometry']
        if geom is None:
            self._add("WARNING", "geometry", fid,
                      "Feature has null geometry",
                      "If intentional, this is valid; if not, check the export source")
            return

        # Layer 3c: Geometry type check
        if not isinstance(geom, dict) or 'type' not in geom:
            self._add("ERROR", "geometry", fid,
                      "Geometry is not a valid object or missing 'type'",
                      "Geometry must be: {\"type\": \"Polygon\", \"coordinates\": [...]}")
            return

        geom_type = geom.get('type')
        if geom_type not in self.VALID_GEOM_TYPES:
            self._add("ERROR", "geometry", fid,
                      f"Invalid geometry type '{geom_type}'",
                      f"Must be one of: {sorted(self.VALID_GEOM_TYPES)}")
            return

        if 'coordinates' not in geom and geom_type != 'GeometryCollection':
            self._add("ERROR", "geometry", fid,
                      f"Geometry of type '{geom_type}' missing 'coordinates'",
                      "Add a 'coordinates' array to the geometry object")
            return

        # Layer 4: Coordinate validity
        coords = geom.get('coordinates', [])
        coord_errors = self._validate_coordinates(coords, geom_type)
        for err_msg, fix in coord_errors:
            self._add("ERROR", "coordinates", fid, err_msg, fix)

        if not coord_errors:
            self._add("INFO", "coordinates", fid,
                      f"{geom_type} coordinates are well-formed")

        # Layer 5: Shapely topology validation (only if coordinates are valid)
        if not coord_errors:
            try:
                shapely_geom = shape(geom)
                if not shapely_geom.is_valid:
                    explanation = explain_validity(shapely_geom)
                    self._add("ERROR", "topology", fid,
                              f"Geometry is topologically invalid: {explanation}",
                              "Fix using shapely: geom.buffer(0) as a quick repair, "
                              "or re-digitize the boundary")
                else:
                    self._add("INFO", "topology", fid,
                              "Topology valid (GEOS check passed)")

                # Layer 5b: Degenerate geometry check
                if geom_type in ('Polygon', 'MultiPolygon') and shapely_geom.area == 0:
                    self._add("ERROR", "topology", fid,
                              "Polygon has zero area — degenerate geometry",
                              "Check that polygon has at least 4 distinct coordinate pairs")

            except Exception as e:
                self._add("ERROR", "topology", fid,
                          f"Could not construct Shapely geometry: {e}",
                          "Check coordinate nesting depth and value types")

        # Layer 6: WGS84 coordinate range check
        if not coord_errors:
            range_errors = self._check_coordinate_ranges(coords, geom_type)
            for err_msg, fix in range_errors:
                self._add("ERROR", "crs", fid, err_msg, fix)

        # Layer 7: Domain-specific business rules
        props = feature.get('properties', {}) or {}
        self._validate_domain_rules(props, fid)

    def _validate_coordinates(self, coords: Any, geom_type: str) -> List[Tuple[str, str]]:
        """
        Validate coordinate structure and values for a given geometry type.
        Returns list of (error_message, fix_suggestion) tuples.
        """
        errors = []

        def check_coord_pair(pair: Any, path: str) -> None:
            """Check a single [lon, lat] pair."""
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                errors.append((
                    f"Invalid coordinate pair at {path}: {pair!r}",
                    "Each coordinate must be [longitude, latitude]"
                ))
                return

            lon, lat = pair[0], pair[1]

            # NaN check
            if isinstance(lon, float) and math.isnan(lon):
                errors.append((
                    f"NaN longitude at {path}: {pair}",
                    "Replace NaN coordinates with valid GPS readings"
                ))
            if isinstance(lat, float) and math.isnan(lat):
                errors.append((
                    f"NaN latitude at {path}: {pair}",
                    "Replace NaN coordinates with valid GPS readings"
                ))

            # Infinity check
            if isinstance(lon, float) and math.isinf(lon):
                errors.append((f"Infinite longitude at {path}", "Invalid coordinate"))
            if isinstance(lat, float) and math.isinf(lat):
                errors.append((f"Infinite latitude at {path}", "Invalid coordinate"))

            # Type check
            if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                errors.append((
                    f"Non-numeric coordinate at {path}: lon={lon!r}, lat={lat!r}",
                    "Coordinates must be numbers, not strings"
                ))

        def check_ring(ring: Any, path: str) -> None:
            """Check a coordinate ring (list of pairs)."""
            if not isinstance(ring, list) or len(ring) < 4:
                errors.append((
                    f"Ring at {path} has {len(ring) if isinstance(ring, list) else '?'} "
                    f"coordinates; minimum is 4 (3 unique + closing repeat)",
                    "Add the first coordinate as the last coordinate to close the ring"
                ))
                return

            for i, pair in enumerate(ring):
                check_coord_pair(pair, f"{path}[{i}]")

            # Check ring closure (first == last)
            if ring[0] != ring[-1]:
                errors.append((
                    f"Ring at {path} is not closed: first={ring[0]}, last={ring[-1]}",
                    "Repeat the first coordinate as the last coordinate"
                ))

        # Dispatch by geometry type
        if geom_type == "Point":
            check_coord_pair(coords, "coordinates")

        elif geom_type == "LineString":
            if not isinstance(coords, list) or len(coords) < 2:
                errors.append(("LineString needs at least 2 coordinate pairs", "Add more points"))
            else:
                for i, pair in enumerate(coords):
                    check_coord_pair(pair, f"coordinates[{i}]")

        elif geom_type == "Polygon":
            if not isinstance(coords, list) or len(coords) == 0:
                errors.append(("Polygon coordinates must be a non-empty list of rings", ""))
            else:
                for r_idx, ring in enumerate(coords):
                    ring_label = "exterior" if r_idx == 0 else f"hole_{r_idx}"
                    check_ring(ring, f"coordinates[{r_idx}] ({ring_label})")

        elif geom_type == "MultiPolygon":
            if not isinstance(coords, list):
                errors.append(("MultiPolygon coordinates must be a list", ""))
            else:
                for p_idx, polygon_coords in enumerate(coords):
                    if not isinstance(polygon_coords, list):
                        errors.append((f"MultiPolygon[{p_idx}] is not a list", ""))
                    else:
                        for r_idx, ring in enumerate(polygon_coords):
                            check_ring(ring, f"coordinates[{p_idx}][{r_idx}]")

        return errors

    def _check_coordinate_ranges(self, coords: Any, geom_type: str) -> List[Tuple[str, str]]:
        """Check that all coordinates are within WGS84 valid range."""
        errors = []

        def check_pair(lon: float, lat: float, path: str) -> None:
            if isinstance(lon, (int, float)) and not math.isnan(lon):
                if not (self.LON_MIN <= lon <= self.LON_MAX):
                    errors.append((
                        f"Longitude {lon:.2f} at {path} is out of WGS84 range [-180, 180]",
                        "Check if coordinates are in a projected CRS (e.g., UTM values like 596000)"
                    ))
            if isinstance(lat, (int, float)) and not math.isnan(lat):
                if not (self.LAT_MIN <= lat <= self.LAT_MAX):
                    errors.append((
                        f"Latitude {lat:.2f} at {path} is out of WGS84 range [-90, 90]",
                        "Verify coordinate order: GeoJSON expects [longitude, latitude], not [lat, lon]"
                    ))

        def flatten_coords(c: Any, depth: int = 0) -> None:
            if depth == 0 and isinstance(c, list) and len(c) >= 2 and isinstance(c[0], (int, float)):
                check_pair(c[0], c[1], "coordinates")
            elif isinstance(c, list):
                for i, item in enumerate(c):
                    if isinstance(item, list) and len(item) >= 2 and isinstance(item[0], (int, float)):
                        check_pair(item[0], item[1], f"coord[{i}]")
                    elif isinstance(item, list):
                        flatten_coords(item, depth + 1)

        flatten_coords(coords)
        return errors

    def _validate_domain_rules(self, props: dict, fid: str) -> None:
        """Layer 7: Business domain validation rules."""

        for field_name, rules in self.domain_rules.items():
            if field_name not in props:
                if rules.get('required', False):
                    self._add("ERROR", "domain_rules", fid,
                              f"Required property '{field_name}' is missing",
                              f"Add '{field_name}' to feature properties")
                continue

            val = props[field_name]

            # Range check for numeric fields
            if 'min' in rules and val is not None:
                try:
                    if float(val) < rules['min']:
                        self._add("WARNING", "domain_rules", fid,
                                  f"'{field_name}' value {val} is below minimum {rules['min']}",
                                  f"Verify the {field_name} value is correct")
                except (TypeError, ValueError):
                    self._add("ERROR", "domain_rules", fid,
                              f"'{field_name}' value {val!r} is not numeric",
                              f"'{field_name}' must be a number")

            if 'max' in rules and val is not None:
                try:
                    if float(val) > rules['max']:
                        self._add("WARNING", "domain_rules", fid,
                                  f"'{field_name}' value {val} exceeds maximum {rules['max']}",
                                  f"Verify the {field_name} value — may be a data entry error")
                except (TypeError, ValueError):
                    pass   # already caught in 'min' check

            # Allowed values check
            if 'allowed' in rules and val is not None:
                if val not in rules['allowed']:
                    self._add("ERROR", "domain_rules", fid,
                              f"'{field_name}' value '{val}' not in allowed list {rules['allowed']}",
                              f"Set '{field_name}' to one of: {rules['allowed']}")

    def generate_report(self) -> str:
        """Generate a formatted validation report string."""
        errors   = [i for i in self.issues if i.severity == "ERROR"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]
        infos    = [i for i in self.issues if i.severity == "INFO"]

        lines = []
        lines.append("=" * 70)
        lines.append("  GeoJSON VALIDATION REPORT")
        lines.append("=" * 70)
        lines.append(f"  Timestamp:  {datetime.utcnow().isoformat()}Z")
        lines.append(f"  Total issues: {len(self.issues)}")
        lines.append(f"    ERRORS:   {len(errors)}")
        lines.append(f"    WARNINGS: {len(warnings)}")
        lines.append(f"    INFO:     {len(infos)}")
        lines.append(f"  PASS/FAIL: {'FAIL' if errors else 'PASS'}")
        lines.append("-" * 70)

        if errors:
            lines.append(f"\n  ERRORS ({len(errors)}):")
            for issue in errors:
                lines.append(str(issue))
                if issue.fix_suggestion:
                    lines.append(f"            FIX: {issue.fix_suggestion}")

        if warnings:
            lines.append(f"\n  WARNINGS ({len(warnings)}):")
            for issue in warnings:
                lines.append(str(issue))
                if issue.fix_suggestion:
                    lines.append(f"            FIX: {issue.fix_suggestion}")

        if infos:
            lines.append(f"\n  INFO ({len(infos)}):")
            for issue in infos:
                lines.append(str(issue))

        lines.append("=" * 70)
        return "\n".join(lines)

    @property
    def is_valid(self) -> bool:
        """True if no ERROR-level issues were found."""
        return not any(i.severity == "ERROR" for i in self.issues)


# ---------------------------------------------------------------------------
# Run validation on the valid dataset
# ---------------------------------------------------------------------------
print("Loading valid GeoJSON dataset for validation...")
with open(VALID_PATH, "r", encoding="utf-8") as f:
    valid_data = json.load(f)

# Domain rules for agricultural field data
domain_rules = {
    "area_ha": {
        "min":      0.1,
        "max":      5000.0,
        "required": True,
    },
    "crop_type": {
        "allowed":  ["corn", "wheat", "soy", "alfalfa", "cotton", "tomato", "grape"],
        "required": True,
    },
    "irrigation_type": {
        "allowed":  ["drip", "flood", "sprinkler", "subsurface", "none"],
        "required": True,
    },
}

validator = GeoJSONValidator(domain_rules=domain_rules)
validator.validate(valid_data)
print(validator.generate_report())

# ---------------------------------------------------------------------------
# Run validation on intentionally broken GeoJSON
# ---------------------------------------------------------------------------
print("\n\nNow testing with INTENTIONALLY BROKEN GeoJSON...")
print("(Demonstrates what the validator catches in production)")
print()

broken_data = {
    "type": "FeatureCollection",
    "features": [
        # Feature 1: Wrong coordinate order (lat/lon instead of lon/lat)
        # Fresno in UTM-style large numbers — validator should flag
        {
            "type": "Feature",
            "id": "BAD-001",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [36.70, -119.71],  # lat/lon swapped — lat first!
                    [36.71, -119.71],
                    [36.71, -119.70],
                    [36.70, -119.70],
                    [36.70, -119.71],
                ]]
            },
            "properties": {
                "field_id": "BAD-001",
                "crop_type": "marijuana",  # not in allowed list
                "area_ha":   -5.0,         # negative area
                "irrigation_type": "drip",
            }
        },
        # Feature 2: Unclosed polygon ring
        {
            "type": "Feature",
            "id": "BAD-002",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-119.71, 36.70],
                    [-119.70, 36.70],
                    [-119.70, 36.71],
                    [-119.71, 36.71],
                    # MISSING closing coordinate: [-119.71, 36.70]
                ]]
            },
            "properties": {
                "field_id": "BAD-002",
                "crop_type": "corn",
                "area_ha": 5.0,
                "irrigation_type": "flood",
            }
        },
        # Feature 3: NaN coordinate
        {
            "type": "Feature",
            "id": "BAD-003",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-119.71, float('nan')],  # NaN latitude from GPS glitch
                    [-119.70, 36.70],
                    [-119.70, 36.71],
                    [-119.71, 36.71],
                    [-119.71, float('nan')],
                ]]
            },
            "properties": {
                "field_id": "BAD-003",
                "crop_type": "wheat",
                "area_ha": 8.2,
                "irrigation_type": "sprinkler",
            }
        },
        # Feature 4: Missing geometry
        {
            "type": "Feature",
            "id": "BAD-004",
            "properties": {
                "field_id": "BAD-004",
                "crop_type": "alfalfa",
                "area_ha": 12.0,
                "irrigation_type": "drip",
            }
            # "geometry" key missing entirely
        },
    ]
}

bad_validator = GeoJSONValidator(domain_rules=domain_rules)
bad_validator.validate(broken_data)
print(bad_validator.generate_report())

print(f"\nValid dataset passes: {validator.is_valid}")
print(f"Broken dataset passes: {bad_validator.is_valid}")
print()
print("PRODUCTION TIP:")
print("  Integrate this validator as a pre-insert check in your ETL pipeline.")
print("  Raise an exception if is_valid == False and route the file to an error queue.")
print("  Log the full report to your observability platform (Datadog, CloudWatch, etc.).")
