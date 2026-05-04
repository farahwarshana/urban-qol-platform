"""
grid_analysis.py
Divides any analysis output into 200m × 200m cells and scores each cell
for Urban Quality of Life (QoL). Score range: 0–100 (100 = best QoL).

Scoring rules per service
--------------------------
NDVI        : higher NDVI → higher score.
              NDVI -1..0 maps to 0, 0..0.2 weak vegetation 20-40,
              0.2..0.5 moderate 40-70, 0.5..1 excellent 70-100.

Heat Index  : comfortable temperature scores high, extremes score low.
              class 0 (< 27°C comfortable) → 100
              class 1 (27-32°C caution)    → 65
              class 2 (32-38°C extreme)    → 30
              class 3 (≥ 38°C danger)      → 5

Crime       : lower crime density → higher score.
              0 crime/km²  → 100, scales down, ≥ 50 crime/km² → 0.

Urban Density: moderate density is best for QoL (too low = poor services,
              too high = overcrowding).
              0-100   /km² → 40  (rural, low services)
              100-500 /km² → 70
              500-2000/km² → 100 (ideal urban)
              2000-5000/km²→ 60
              >5000   /km² → 25  (overcrowded)

Facility Accessibility: smaller walk time → higher score.
              5 min zone  → 100
              10 min zone → 65
              15 min zone → 35
              outside     → 0

Public Transport: cell is inside transit walking coverage → high score.
              covered (type="covered")   → 100
              uncovered (type="uncovered") → 0
              (score is interpolated from coverage fraction for partial cells)
"""

import numpy as np
import rasterio
import geopandas as gpd
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import box, mapping
from pyproj import Transformer


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_utm_crs(lon, lat):
    """Return the EPSG code for the UTM zone covering (lon, lat)."""
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


_GRID_TARGET_CELLS = 650   # target cell count (cols × rows ≈ this)
_CELL_MIN_M        = 50    # absolute floor — sub-block detail


def _adaptive_cell_size(bounds_4326):
    """
    Derive cell size so that cols × rows ≈ _GRID_TARGET_CELLS for *any* extent,
    from a single city block to multiple countries.

    Formula:  cell_m = sqrt(width_m × height_m / TARGET)

    The raw result is then rounded to the nearest "clean" value using a
    scale-relative rounding base:
      raw < 500 m  → round to nearest 25 m
      raw < 2 km   → round to nearest 100 m
      raw < 10 km  → round to nearest 500 m
      raw < 50 km  → round to nearest 2 000 m
      raw ≥ 50 km  → round to nearest 10 000 m

    No upper clamp — for country-scale data the cell will simply be large.
    """
    minx, miny, maxx, maxy = bounds_4326
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    utm_epsg = _get_utm_crs(cx, cy)
    to_utm   = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)

    x0, y0 = to_utm.transform(minx, miny)
    x1, y1 = to_utm.transform(maxx, maxy)
    width_m  = abs(x1 - x0)
    height_m = abs(y1 - y0)

    raw = (width_m * height_m / _GRID_TARGET_CELLS) ** 0.5

    # Scale-relative rounding — keeps values clean at every zoom level
    if raw < 500:
        base = 25
    elif raw < 2_000:
        base = 100
    elif raw < 10_000:
        base = 500
    elif raw < 50_000:
        base = 2_000
    else:
        base = 10_000

    cell_m = max(_CELL_MIN_M, round(raw / base) * base)
    # Safety: if rounding pushed us to 0, use the base itself
    if cell_m == 0:
        cell_m = base

    return int(cell_m)


def _build_grid_cells(bounds_4326):
    """
    Given a bounding box in WGS84 degrees, return a GeoDataFrame of
    adaptive-size cells in EPSG:4326.  Cell size is chosen automatically
    so the grid never exceeds ~600 cells regardless of area extent.

    Returns
    -------
    (GeoDataFrame with polygon geometry column CRS=EPSG:4326, cell_m used)
    """
    minx, miny, maxx, maxy = bounds_4326
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    cell_m = _adaptive_cell_size(bounds_4326)

    utm_epsg = _get_utm_crs(cx, cy)
    to_utm   = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    to_wgs84 = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)

    x0, y0 = to_utm.transform(minx, miny)
    x1, y1 = to_utm.transform(maxx, maxy)

    xs = np.arange(x0, x1, cell_m)
    ys = np.arange(y0, y1, cell_m)

    cells = []
    for xi in xs:
        for yi in ys:
            corners_utm = [
                (xi,          yi),
                (xi + cell_m, yi),
                (xi + cell_m, yi + cell_m),
                (xi,          yi + cell_m),
            ]
            corners_wgs = [to_wgs84.transform(px, py) for px, py in corners_utm]
            cells.append(box(
                min(p[0] for p in corners_wgs),
                min(p[1] for p in corners_wgs),
                max(p[0] for p in corners_wgs),
                max(p[1] for p in corners_wgs),
            ))

    gdf = gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")
    return gdf, cell_m


# ── Scoring functions  (4 tiers each, 0–100) ─────────────────────────────────
#
# Tier labels used across all services:
#   Tier 4 — Excellent  (75–100)  green
#   Tier 3 — Good       (50– 74)  yellow-green
#   Tier 2 — Poor       (25– 49)  orange
#   Tier 1 — Bad        ( 0– 24)  red
#
# Every scoring function maps the raw output value to a continuous 0–100 score
# whose shape reflects what is actually beneficial for urban quality of life.
# ─────────────────────────────────────────────────────────────────────────────


def _score_ndvi(value):
    """
    NDVI (-1 … 1) → QoL score.

    Urban QoL ideal: dense healthy vegetation (NDVI 0.5–1.0).
    Bare soil / sparse cover still liveable but not ideal.
    Water / non-vegetated surfaces (negative NDVI) are not scored.

    Tier 4 Excellent : 0.50 – 1.00  → 75–100  (dense healthy greenery)
    Tier 3 Good      : 0.20 – 0.50  → 50– 74  (sparse-to-moderate cover)
    Tier 2 Poor      : 0.00 – 0.20  → 25– 49  (very little vegetation)
    Tier 1 Bad       : -0.10 – 0.00 → 0 – 24  (bare soil / built surface)
    Non-vegetated (< -0.10) → None (no data / water)
    """
    if np.isnan(value) or value < -0.10:
        return None
    if value < 0.00:
        return int(np.interp(value, [-0.10, 0.00], [0, 24]))
    if value < 0.20:
        return int(np.interp(value, [0.00, 0.20], [25, 49]))
    if value < 0.50:
        return int(np.interp(value, [0.20, 0.50], [50, 74]))
    return int(np.interp(min(value, 1.0), [0.50, 1.00], [75, 100]))


def _score_heat_index(cls_value):
    """
    Heat index class (0–3) → QoL score.

    The backend outputs integer classes:
      0 = comfortable  (< 27 °C)
      1 = caution      (27–32 °C)
      2 = extreme      (32–38 °C)
      3 = danger       (≥ 38 °C)

    Tier 4 Excellent : class 0 → 90   (comfortable, ideal outdoor conditions)
    Tier 3 Good      : class 1 → 65   (warm but tolerable)
    Tier 2 Poor      : class 2 → 30   (uncomfortably hot, discourages outdoor use)
    Tier 1 Bad       : class 3 → 8    (dangerously hot, major QoL penalty)
    """
    lut = {0: 90, 1: 65, 2: 30, 3: 8}
    if np.isnan(cls_value) or cls_value < 0:
        return None
    return lut.get(int(round(cls_value)), None)


def _score_crime(density):
    """
    Crime density (incidents / km²) → QoL score.

    Lower crime is strictly better; there is no "too low" crime.
    Thresholds are calibrated to typical urban crime-density ranges.

    Tier 4 Excellent : 0   – 5   /km² → 75–100  (very safe)
    Tier 3 Good      : 5   – 20  /km² → 50– 74  (occasional incidents)
    Tier 2 Poor      : 20  – 60  /km² → 25– 49  (frequent incidents)
    Tier 1 Bad       : 60  – 150+/km² →  0– 24  (high crime, unsafe)
    """
    if np.isnan(density) or density < 0:
        return None
    if density <= 5:
        return int(np.interp(density, [0, 5], [100, 75]))
    if density <= 20:
        return int(np.interp(density, [5, 20], [74, 50]))
    if density <= 60:
        return int(np.interp(density, [20, 60], [49, 25]))
    return int(np.interp(min(density, 150), [60, 150], [24, 0]))


def _score_urban_density(density):
    """
    Population density (people / km²) → QoL score.

    Urban QoL peaks at moderate density: enough people for good services,
    parks, transit, but not so many that overcrowding degrades livability.

    Tier 4 Excellent : 1 000 – 5 000 /km² → 75–100  (vibrant mixed-use urban)
    Tier 3 Good      :   200 – 1 000 /km² → 50– 74  (suburban / low urban)
                      : 5 000 –12 000 /km² → 74– 50  (dense urban, still OK)
    Tier 2 Poor      :    50 –   200 /km² → 25– 49  (sparse, poor services)
                      :12 000 –25 000 /km² → 49– 25  (overcrowded)
    Tier 1 Bad       :     0 –    50 /km² →  0– 24  (rural / no services)
                      :   >25 000    /km² →  0– 24  (extreme overcrowding)
    """
    if np.isnan(density) or density < 0:
        return None
    # rising side
    if density < 50:
        return int(np.interp(density, [0, 50], [0, 24]))
    if density < 200:
        return int(np.interp(density, [50, 200], [25, 49]))
    if density < 1000:
        return int(np.interp(density, [200, 1000], [50, 74]))
    if density < 5000:
        return int(np.interp(density, [1000, 5000], [75, 100]))
    # falling side — overcrowding
    if density < 12000:
        return int(np.interp(density, [5000, 12000], [100, 50]))
    if density < 25000:
        return int(np.interp(density, [12000, 25000], [49, 25]))
    return int(np.interp(min(density, 50000), [25000, 50000], [24, 0]))


def _score_facility_accessibility(walk_time_min):
    """
    Walk time to nearest facility (minutes) → QoL score.

    The closer a facility, the higher the score.  There is no penalty for
    being "too close" — maximum accessibility is always best.

    Tier 4 Excellent :  0 – 5  min → 100– 75  (immediate neighbourhood)
    Tier 3 Good      :  5 – 10 min →  74– 50  (short walk)
    Tier 2 Poor      : 10 – 20 min →  49– 25  (long walk, limits usage)
    Tier 1 Bad       : 20 – 30+min →  24–  0  (effectively inaccessible on foot)
    Outside all zones: 0 (no access)
    """
    if walk_time_min is None:
        return 0
    if walk_time_min <= 5:
        return int(np.interp(walk_time_min, [0, 5], [100, 75]))
    if walk_time_min <= 10:
        return int(np.interp(walk_time_min, [5, 10], [74, 50]))
    if walk_time_min <= 20:
        return int(np.interp(walk_time_min, [10, 20], [49, 25]))
    return int(np.interp(min(walk_time_min, 30), [20, 30], [24, 0]))


# ── Per-service grid builders ─────────────────────────────────────────────────

def grid_from_raster(raster_path, service_type):
    """
    Sample a single-band GeoTIFF on an adaptive grid and return a GeoJSON dict.
    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    score_fn = _score_ndvi if service_type == "ndvi" else _score_heat_index

    with rasterio.open(raster_path) as src:
        bounds    = src.bounds
        nodata    = src.nodata if src.nodata is not None else -9999
        data      = src.read(1).astype("float32")
        transform = src.transform

    bounds_4326 = (bounds.left, bounds.bottom, bounds.right, bounds.top)
    grid, cell_m = _build_grid_cells(bounds_4326)

    features = []
    for _, row in grid.iterrows():
        geom = row.geometry
        cx   = geom.centroid.x
        cy   = geom.centroid.y

        try:
            col, r = ~transform * (cx, cy)
            col, r = int(col), int(r)
            h, w   = data.shape
            if 0 <= r < h and 0 <= col < w:
                val = float(data[r, col])
                if val == nodata or val == -9999:
                    val = np.nan
            else:
                val = np.nan
        except Exception:
            val = np.nan

        score = score_fn(val) if not np.isnan(val) else None

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "value":     round(val, 4) if not np.isnan(val) else None,
                "qol_score": score,
                "service":   service_type,
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }


def grid_from_vector(geojson_path, service_type, value_field):
    """
    Overlay an adaptive grid on a polygon GeoJSON, inherit each cell's value
    from the underlying polygon, and score it.
    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    score_fn = _score_crime if service_type == "crime" else _score_urban_density

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    bounds       = gdf.total_bounds   # minx, miny, maxx, maxy
    grid, cell_m = _build_grid_cells(tuple(bounds))

    joined = gpd.sjoin(grid, gdf[[value_field, "geometry"]], how="left", predicate="intersects")

    if joined.index.duplicated().any():
        joined = joined.groupby(joined.index)[value_field].mean().to_frame()
        joined = joined.join(grid.geometry)
        joined = gpd.GeoDataFrame(joined, geometry="geometry", crs="EPSG:4326")
    else:
        joined = gpd.GeoDataFrame(joined, geometry="geometry", crs="EPSG:4326")

    features = []
    for _, row in joined.iterrows():
        geom = row.geometry
        val  = row.get(value_field, np.nan)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            val = np.nan

        score = score_fn(float(val)) if not (isinstance(val, float) and np.isnan(val)) else None

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "value":     round(float(val), 4) if not (isinstance(val, float) and np.isnan(val)) else None,
                "qol_score": score,
                "service":   service_type,
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }


def _score_transit_coverage(coverage_fraction):
    """
    Fraction of cell area covered by transit buffers (0.0–1.0) → QoL score.

    Tier 4 Excellent : 0.75 – 1.00 → 75–100  (well-served)
    Tier 3 Good      : 0.50 – 0.75 → 50– 74  (partially served)
    Tier 2 Poor      : 0.25 – 0.50 → 25– 49  (low coverage)
    Tier 1 Bad       : 0.00 – 0.25 →  0– 24  (effectively uncovered)
    """
    if coverage_fraction is None or np.isnan(coverage_fraction):
        return None
    f = float(np.clip(coverage_fraction, 0.0, 1.0))
    if f >= 0.75:
        return int(np.interp(f, [0.75, 1.00], [75, 100]))
    if f >= 0.50:
        return int(np.interp(f, [0.50, 0.75], [50, 74]))
    if f >= 0.25:
        return int(np.interp(f, [0.25, 0.50], [25, 49]))
    return int(np.interp(f, [0.00, 0.25], [0, 24]))


def grid_from_transit_coverage(geojson_path):
    """
    Score cells based on how much of each cell falls inside transit walking
    coverage polygons.  Expects a GeoJSON with a 'type' property of
    'covered' or 'uncovered' (as produced by calculate_transit_coverage).

    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    if gdf.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    bounds       = gdf.total_bounds
    grid, cell_m = _build_grid_cells(tuple(bounds))

    # Keep only covered polygons for intersection
    covered_gdf = gdf[gdf.get("type", gdf.get("type", None)) == "covered"] if "type" in gdf.columns else gdf
    if covered_gdf.empty:
        # Fallback: treat all features as covered
        covered_gdf = gdf

    covered_union = covered_gdf.geometry.union_all()

    # Determine UTM for accurate area fraction
    cx = (bounds[0] + bounds[2]) / 2
    cy = (bounds[1] + bounds[3]) / 2
    utm_epsg = _get_utm_crs(cx, cy)
    utm_crs  = f"EPSG:{utm_epsg}"

    grid_utm         = grid.to_crs(utm_crs)
    covered_gdf_utm  = covered_gdf.to_crs(utm_crs)
    covered_union_utm = covered_gdf_utm.geometry.union_all()

    features = []
    for idx, row in grid_utm.iterrows():
        cell_geom  = row.geometry
        cell_area  = cell_geom.area
        cell_wgs   = grid.loc[idx].geometry

        if cell_area <= 0:
            fraction = 0.0
        else:
            intersection = cell_geom.intersection(covered_union_utm)
            fraction     = intersection.area / cell_area if not intersection.is_empty else 0.0

        score = _score_transit_coverage(fraction)

        features.append({
            "type": "Feature",
            "geometry": cell_wgs.__geo_interface__,
            "properties": {
                "value":     round(fraction, 4),
                "qol_score": score,
                "service":   "public-transport",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }


def grid_from_facility_accessibility(geojson_path):
    """
    Score cells based on the minimum walk time from a facility accessibility
    isochrone GeoJSON (zones for 5/10/15 min).
    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    bounds       = gdf.total_bounds
    grid, cell_m = _build_grid_cells(tuple(bounds))

    time_col = None
    for candidate in ["walk_time", "time_min", "minutes", "travel_time"]:
        if candidate in gdf.columns:
            time_col = candidate
            break

    features = []
    for _, row in grid.iterrows():
        geom     = row.geometry
        centroid = geom.centroid
        pt       = gpd.GeoDataFrame(geometry=[centroid], crs="EPSG:4326")

        joined = gpd.sjoin(pt, gdf, how="left", predicate="within")

        if time_col and not joined.empty and time_col in joined.columns:
            times     = joined[time_col].dropna()
            walk_time = float(times.min()) if len(times) > 0 else None
        else:
            walk_time = 5 if (not joined.empty and len(joined) > 0) else None

        score = _score_facility_accessibility(walk_time)

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "value":     walk_time,
                "qol_score": score,
                "service":   "facility-accessibility",
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }
