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

Facility Accessibility: smaller walk time → higher score (dynamic intervals).
              smallest interval zone → 100
              each subsequent zone   → 100 - (100/n * i)   where n = interval count
              outside all zones      → 0

Public Transport: cell is inside transit walking coverage → high score.
              covered (type="covered")   → 100
              uncovered (type="uncovered") → 0
              (score is interpolated from coverage fraction for partial cells)

Air Quality Index: lower AQI class → higher score.
              class 0 (Good)           → 95
              class 1 (Moderate)       → 70
              class 2 (Sensitive)      → 45
              class 3 (Unhealthy)      → 25
              class 4 (Very Unhealthy) → 10
              class 5 (Hazardous)      →  0

Vegetation Density: benchmarked against the 30% urban greenery standard.
              >= 50% vegetated → 75–100  (excellent, well above benchmark)
              30–50% vegetated → 50– 74  (good, at/above benchmark)
              15–30% vegetated → 25– 49  (poor, below benchmark)
               0–15% vegetated →  0– 24  (bad, severely under-greened)
"""

import math
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import box, mapping
from shapely.ops import unary_union


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_utm_crs(lon, lat):
    """Return the EPSG code for the UTM zone covering (lon, lat)."""
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


_GRID_TARGET_CELLS = 650   # target cell count (cols × rows ≈ this)
_CELL_MIN_M        = 50    # absolute floor — sub-block detail


def _adaptive_cell_size(bounds_4326):
    """
    Derive cell size so that cols × rows ≈ _GRID_TARGET_CELLS for *any* extent.
    Uses degree-to-metre approximation only — no pyproj/Transformer needed.

    Formula:  cell_m = sqrt(width_m × height_m / TARGET)

    The raw result is rounded to the nearest "clean" value using a
    scale-relative rounding base.
    """
    minx, miny, maxx, maxy = bounds_4326
    cy = (miny + maxy) / 2

    # 1 degree latitude ≈ 111 000 m; longitude degree shrinks with cos(lat)
    lat_rad  = math.radians(cy)
    width_m  = abs(maxx - minx) * 111_000 * math.cos(lat_rad)
    height_m = abs(maxy - miny) * 111_000

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
    if cell_m == 0:
        cell_m = base

    return int(cell_m)


def _build_grid_cells(bounds_4326):
    """
    Given a bounding box in WGS84 degrees, return a GeoDataFrame of
    adaptive-size cells in EPSG:4326.  Cell size is chosen automatically
    so the grid never exceeds ~600 cells regardless of area extent.

    Uses geopandas .to_crs() for reprojection (rasterio-bundled PROJ, no pyproj).

    Returns
    -------
    (GeoDataFrame with polygon geometry column CRS=EPSG:4326, cell_m used)
    """
    minx, miny, maxx, maxy = bounds_4326
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    cell_m   = _adaptive_cell_size(bounds_4326)
    utm_epsg = _get_utm_crs(cx, cy)
    utm_crs  = f"EPSG:{utm_epsg}"

    # Project the bounding box corners to UTM via geopandas (no pyproj import)
    corners_gdf = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([minx, maxx], [miny, maxy]),
        crs="EPSG:4326",
    ).to_crs(utm_crs)
    x0, y0 = corners_gdf.geometry.iloc[0].x, corners_gdf.geometry.iloc[0].y
    x1, y1 = corners_gdf.geometry.iloc[1].x, corners_gdf.geometry.iloc[1].y

    xs = np.arange(x0, x1, cell_m)
    ys = np.arange(y0, y1, cell_m)

    # Build UTM cell boxes, then reproject the batch to WGS84
    utm_boxes = [
        box(xi, yi, xi + cell_m, yi + cell_m)
        for xi in xs
        for yi in ys
    ]

    if not utm_boxes:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), cell_m

    gdf_utm = gpd.GeoDataFrame(geometry=utm_boxes, crs=utm_crs)
    gdf     = gdf_utm.to_crs("EPSG:4326")
    return gdf, cell_m


def _build_grid_cells_n(bounds_4326, target_cells):
    """Like _build_grid_cells but with a caller-supplied target cell count."""
    minx, miny, maxx, maxy = bounds_4326
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    lat_rad  = math.radians((miny + maxy) / 2)
    width_m  = abs(maxx - minx) * 111_000 * math.cos(lat_rad)
    height_m = abs(maxy - miny) * 111_000
    raw = (width_m * height_m / target_cells) ** 0.5

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
    if cell_m == 0:
        cell_m = base
    cell_m = int(cell_m)

    utm_epsg = _get_utm_crs(cx, cy)
    utm_crs  = f"EPSG:{utm_epsg}"

    corners_gdf = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([minx, maxx], [miny, maxy]),
        crs="EPSG:4326",
    ).to_crs(utm_crs)
    x0, y0 = corners_gdf.geometry.iloc[0].x, corners_gdf.geometry.iloc[0].y
    x1, y1 = corners_gdf.geometry.iloc[1].x, corners_gdf.geometry.iloc[1].y

    xs = np.arange(x0, x1, cell_m)
    ys = np.arange(y0, y1, cell_m)

    utm_boxes = [box(xi, yi, xi + cell_m, yi + cell_m) for xi in xs for yi in ys]
    if not utm_boxes:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), cell_m

    gdf_utm = gpd.GeoDataFrame(geometry=utm_boxes, crs=utm_crs)
    gdf     = gdf_utm.to_crs("EPSG:4326")
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

    The WHO / urban-planning recommended healthy density is 5,000 pop/km².
    Scores peak at exactly 5,000 and fall symmetrically in both directions:
    too sparse means poor services; too dense means overcrowding.

    Below 5,000 (under-populated):
      5 000 → 100   (optimal)
      2 500 →  75   (good)
        500 →  50   (fair — suburban fringe)
        100 →  25   (poor — sparse)
          0 →   0   (no population)

    Above 5,000 (over-populated):
      5 000 → 100   (optimal)
     10 000 →  75   (still liveable)
     20 000 →  50   (crowded)
     35 000 →  25   (severely overcrowded)
     50 000 →   0   (extreme)
    """
    if density is None or (isinstance(density, float) and np.isnan(density)) or density < 0:
        return None
    OPTIMAL = 5000
    if density <= OPTIMAL:
        # under-populated side
        if density >= 2500:
            return int(np.interp(density, [2500, OPTIMAL], [75, 100]))
        if density >= 500:
            return int(np.interp(density, [500, 2500], [50, 75]))
        if density >= 100:
            return int(np.interp(density, [100, 500], [25, 50]))
        return int(np.interp(density, [0, 100], [0, 25]))
    else:
        # over-populated side
        if density <= 10000:
            return int(np.interp(density, [OPTIMAL, 10000], [100, 75]))
        if density <= 20000:
            return int(np.interp(density, [10000, 20000], [75, 50]))
        if density <= 35000:
            return int(np.interp(density, [20000, 35000], [50, 25]))
        return int(np.interp(min(density, 50000), [35000, 50000], [25, 0]))


def _score_aqi(cls_value):
    """
    AQI class (0–5) → QoL score.

    The backend outputs integer classes:
      0 = Good              (AQI  0– 50)
      1 = Moderate          (AQI 51–100)
      2 = Sensitive groups  (AQI 101–150)
      3 = Unhealthy         (AQI 151–200)
      4 = Very Unhealthy    (AQI 201–300)
      5 = Hazardous         (AQI >300)

    Tier 4 Excellent : class 0 → 95  (clean air)
    Tier 3 Good      : class 1 → 70  (acceptable)
    Tier 2 Poor      : class 2 → 45  (sensitive groups affected)
                     : class 3 → 25  (unhealthy for all)
    Tier 1 Bad       : class 4 → 10  (very unhealthy)
                     : class 5 →  0  (hazardous)
    """
    lut = {0: 95, 1: 70, 2: 45, 3: 25, 4: 10, 5: 0}
    if np.isnan(cls_value) or cls_value < 0:
        return None
    return lut.get(int(round(cls_value)), None)


def _score_facility_accessibility(walk_time_min, sorted_times=None):
    """
    Walk time to nearest facility zone → QoL score (dynamic, interval-aware).

    When sorted_times is provided the score is computed as equal steps:
      smallest interval → 100
      next interval     → 100 - step
      ...
      largest interval  → step   (always > 0)
      outside all zones → 0

    step = 100 / len(sorted_times)

    Without sorted_times falls back to the fixed legacy thresholds.
    """
    if walk_time_min is None:
        return 0

    if sorted_times:
        n = len(sorted_times)
        step = 100.0 / n
        for i, t in enumerate(sorted_times):
            if walk_time_min <= t:
                return int(round(100.0 - i * step))
        return 0

    # Legacy fallback
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
    Only cells whose centroid falls on valid (non-nodata) raster pixels are kept.
    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    if service_type == "ndvi":
        score_fn = _score_ndvi
    elif service_type == "air-quality":
        score_fn = _score_aqi
    else:
        score_fn = _score_heat_index

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

        # Skip cells with no valid data — they are outside the analysis extent
        if np.isnan(val):
            continue

        score = score_fn(val)
        # Also skip if the scoring function itself considers the value out-of-range
        if score is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "value":     round(val, 4),
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
    Cells whose centroid does not fall inside any input polygon are dropped —
    they are outside the analysis boundary and must not affect statistics.
    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    score_fn = _score_crime if service_type == "crime" else _score_urban_density

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    bounds       = gdf.total_bounds   # minx, miny, maxx, maxy
    grid, cell_m = _build_grid_cells(tuple(bounds))

    # Boundary filter: keep only cells whose centroid is inside the data bbox
    minx, miny, maxx, maxy = bounds
    centroids = grid.geometry.centroid
    in_bounds = (
        (centroids.x >= minx) & (centroids.x <= maxx) &
        (centroids.y >= miny) & (centroids.y <= maxy)
    )
    grid = grid[in_bounds].copy()

    # Join values from the polygons
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
            continue  # still no data after join — drop silently

        score = score_fn(float(val))
        if score is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "value":     round(float(val), 4),
                "qol_score": score,
                "service":   service_type,
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }


def _score_transit_distance(dist_m):
    """
    Distance from cell centroid to nearest station (metres) → QoL score 0–100.

    Excellent : 0 – 300 m   → 100 – 75   (direct / very close access)
    Good      : 300 – 600 m → 74  – 50   (comfortable walk)
    Fair      : 600 – 1000 m→ 49  – 25   (acceptable but long)
    Poor      : > 1000 m    → 24  –  0   (underserved; score floors at 0 at 2000 m+)
    """
    if dist_m is None or np.isnan(dist_m):
        return 0
    d = float(dist_m)
    if d <= 300:
        return int(np.interp(d, [0, 300],   [100, 75]))
    if d <= 600:
        return int(np.interp(d, [300, 600], [74, 50]))
    if d <= 1000:
        return int(np.interp(d, [600, 1000],[49, 25]))
    return int(max(0, np.interp(d, [1000, 2000], [24, 0])))


def grid_from_transit_coverage(geojson_path):
    """
    Score cells for public-transport QoL based on distance to nearest station.

    The input GeoJSON contains features tagged by their 'layer' property:
        layer == "station"   — transit station points
        layer == "boundary"  — AOI outline polygon(s)
        (no layer / type)    — covered / uncovered area polygons

    Each cell centroid's distance to the nearest station is computed in UTM
    (metres) and mapped to a 0–100 score:
        0–300 m   → 100–75  (Excellent)
        300–600 m → 74–50   (Good)
        600–1000 m→ 49–25   (Fair)
        >1000 m   → 24–0    (Poor, floors at 0 beyond 2000 m)
    """
    from scipy.spatial import cKDTree

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    if gdf.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    # Split by layer tag
    layer_col = "layer" if "layer" in gdf.columns else None
    if layer_col:
        stations_gdf  = gdf[gdf[layer_col] == "station"].copy()
        boundary_gdf  = gdf[gdf[layer_col] == "boundary"].copy()
        coverage_gdf  = gdf[~gdf[layer_col].isin(["station", "boundary"])].copy()
    else:
        stations_gdf  = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        boundary_gdf  = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        coverage_gdf  = gdf.copy()

    # AOI comes from boundary layer; fall back to coverage polygons if absent
    if not boundary_gdf.empty:
        aoi_gdf = boundary_gdf
    elif not coverage_gdf.empty:
        aoi_gdf = coverage_gdf
    else:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    bounds       = aoi_gdf.total_bounds
    grid, cell_m = _build_grid_cells(tuple(bounds))

    if grid.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": cell_m}

    # Project to UTM for metric distances
    centroid_wgs = aoi_gdf.geometry.union_all().centroid
    lon, lat = centroid_wgs.x, centroid_wgs.y
    utm_zone  = int((lon + 180) / 6) + 1
    utm_epsg  = (32600 if lat >= 0 else 32700) + utm_zone
    utm_crs   = f"EPSG:{utm_epsg}"

    aoi_utm  = aoi_gdf.to_crs(utm_crs)
    grid_utm = grid.to_crs(utm_crs)

    # AOI boundary filter: keep only cells whose centroid is inside the AOI
    aoi_union = aoi_utm.geometry.union_all().buffer(0)
    centroids_utm = grid_utm.geometry.centroid
    in_aoi = centroids_utm.apply(lambda pt: aoi_union.contains(pt))
    grid_utm = grid_utm[in_aoi].copy()
    centroids_utm = grid_utm.geometry.centroid

    if grid_utm.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": cell_m}

    # Build distance lookup using station points
    if not stations_gdf.empty:
        stations_utm = stations_gdf.to_crs(utm_crs)
        station_coords = np.array([(g.x, g.y) for g in stations_utm.geometry])
        tree = cKDTree(station_coords)
        centroid_coords = np.array([(pt.x, pt.y) for pt in centroids_utm])
        dists_m, _ = tree.query(centroid_coords)
    else:
        # No stations embedded — fall back to covered/uncovered binary
        coverage_gdf_clean = coverage_gdf.copy()
        coverage_gdf_clean["geometry"] = coverage_gdf_clean.geometry.buffer(0)
        coverage_gdf_clean = coverage_gdf_clean[coverage_gdf_clean.geometry.is_valid]
        covered_gdf = coverage_gdf_clean[coverage_gdf_clean.get("type") == "covered"] if "type" in coverage_gdf_clean.columns else coverage_gdf_clean
        centroids_gdf = gpd.GeoDataFrame(
            {"cell_idx": grid_utm.index},
            geometry=centroids_utm.values,
            crs=utm_crs,
        ).set_index("cell_idx")
        if not covered_gdf.empty:
            joined = gpd.sjoin(centroids_gdf, covered_gdf[["geometry"]].to_crs(utm_crs), how="left", predicate="within")
            covered_set = set(joined[joined["index_right"].notna()].index)
        else:
            covered_set = set()
        dists_m = np.array([0.0 if idx in covered_set else 1500.0 for idx in grid_utm.index])

    # Reproject grid cells back to WGS84 for GeoJSON output
    grid_wgs = grid_utm.to_crs("EPSG:4326")

    features = []
    for i, (idx, row) in enumerate(grid_wgs.iterrows()):
        dist = float(dists_m[i])
        score = _score_transit_distance(dist)

        features.append({
            "type": "Feature",
            "geometry": mapping(row.geometry),
            "properties": {
                "value":     round(dist / 1000.0, 3),
                "qol_score": score,
                "dist_m":    round(dist, 1),
                "service":   "public-transport",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }


_FACILITY_GRID_TARGET_CELLS = 1200   # denser grid for facility accessibility


def grid_from_facility_accessibility(geojson_path):
    """
    Score cells based on the minimum walk time from a facility accessibility
    isochrone GeoJSON.

    Scoring is dynamic: the user-provided time intervals are read from the
    zone features and equal score steps are assigned:
      smallest interval → 100, next → 100-step, ..., outside all zones → 0
    where step = 100 / number_of_intervals.

    When a boundary feature (layer == "boundary") is present the grid covers
    the full AOI and every cell inside it is scored — cells outside all
    isochrone zones get qol_score 0 (no access).  Without a boundary the grid
    covers only the union of isochrone zones.
    """
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    if gdf.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    # ── Split features by role ────────────────────────────────────────────────
    has_boundary = "layer" in gdf.columns and (gdf["layer"] == "boundary").any()

    if has_boundary:
        boundary_gdf = gdf[gdf["layer"] == "boundary"].copy()
    else:
        boundary_gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    # Zone features: anything that is not a boundary outline or an uncovered polygon
    keep = np.ones(len(gdf), dtype=bool)
    if "type" in gdf.columns:
        keep &= ~gdf["type"].isin({"uncovered"}).values
    if "layer" in gdf.columns:
        keep &= ~gdf["layer"].isin({"boundary"}).values
    zone_gdf = gdf[keep].copy()

    if zone_gdf.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    # ── Extract sorted time intervals from zone data ──────────────────────────
    time_col = None
    for candidate in ["time_min", "walk_time", "minutes", "travel_time"]:
        if candidate in zone_gdf.columns:
            time_col = candidate
            break

    sorted_times = None
    if time_col:
        raw_times = zone_gdf[time_col].dropna().unique()
        if len(raw_times) > 0:
            sorted_times = sorted([int(t) for t in raw_times])

    # ── Grid extent and cell size (denser than default) ───────────────────────
    extent_gdf = boundary_gdf if has_boundary else zone_gdf
    bounds     = extent_gdf.total_bounds

    grid, cell_m = _build_grid_cells_n(tuple(bounds), _FACILITY_GRID_TARGET_CELLS)

    if grid.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": cell_m}

    # ── Project to UTM for accurate containment tests ─────────────────────────
    cx = (bounds[0] + bounds[2]) / 2
    cy = (bounds[1] + bounds[3]) / 2
    utm_zone = int((cx + 180) / 6) + 1
    utm_epsg = (32600 if cy >= 0 else 32700) + utm_zone
    utm_crs  = f"EPSG:{utm_epsg}"

    grid_utm      = grid.to_crs(utm_crs)
    centroids_utm = grid_utm.geometry.centroid

    # ── Clip grid to AOI boundary (or zone union when no boundary given) ──────
    if has_boundary:
        aoi_union_utm = (
            gpd.GeoDataFrame(geometry=[unary_union(boundary_gdf.geometry)], crs="EPSG:4326")
            .to_crs(utm_crs)
            .geometry.iloc[0]
            .buffer(0)
        )
    else:
        aoi_union_utm = (
            gpd.GeoDataFrame(geometry=[unary_union(zone_gdf.geometry)], crs="EPSG:4326")
            .to_crs(utm_crs)
            .geometry.iloc[0]
            .buffer(0)
        )

    in_aoi   = centroids_utm.apply(lambda pt: aoi_union_utm.contains(pt))
    grid_utm = grid_utm[in_aoi].copy()

    if grid_utm.empty:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": cell_m}

    # ── Spatial join: centroid within isochrone zone ──────────────────────────
    centroids_gdf = gpd.GeoDataFrame(
        geometry=grid_utm.geometry.centroid.values,
        index=grid_utm.index,
        crs=utm_crs,
    ).to_crs("EPSG:4326")

    joined = gpd.sjoin(centroids_gdf, zone_gdf, how="left", predicate="within")

    grid_wgs = grid_utm.to_crs("EPSG:4326")

    features = []
    for idx, row in grid_wgs.iterrows():
        matches = joined.loc[[idx]] if idx in joined.index else joined.iloc[0:0]

        if matches.empty or matches["index_right"].isna().all():
            if has_boundary:
                features.append({
                    "type": "Feature",
                    "geometry": mapping(row.geometry),
                    "properties": {
                        "value":     None,
                        "qol_score": 0,
                        "service":   "facility-accessibility",
                    },
                })
            continue

        if time_col and time_col in matches.columns:
            times     = matches[time_col].dropna()
            walk_time = float(times.min()) if len(times) > 0 else None
        else:
            walk_time = None

        features.append({
            "type": "Feature",
            "geometry": mapping(row.geometry),
            "properties": {
                "value":     walk_time,
                "qol_score": _score_facility_accessibility(walk_time, sorted_times),
                "service":   "facility-accessibility",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "cell_size_m": cell_m,
    }


def _score_vegetation_pct(pct):
    """
    Vegetation % per cell → QoL score (0–100).
    Benchmarked against the 30% urban greenery standard.

    Tier 4 Excellent : >= 50%  → 75–100  (well above benchmark)
    Tier 3 Good      : 30–50%  → 50– 74  (at or above benchmark)
    Tier 2 Poor      : 15–30%  → 25– 49  (below benchmark)
    Tier 1 Bad       :  0–15%  →  0– 24  (severely under-greened)
    """
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return None
    p = float(np.clip(pct, 0.0, 100.0))
    if p >= 50:
        return int(np.interp(p, [50, 100], [75, 100]))
    if p >= 30:
        return int(np.interp(p, [30, 50], [50, 74]))
    if p >= 15:
        return int(np.interp(p, [15, 30], [25, 49]))
    return int(np.interp(p, [0, 15], [0, 24]))


def _score_traffic(local_density, congestion):
    """
    Road density + congestion label → QoL score (0–100).

    Lower congestion and optimal road density → higher QoL.

    Tier 4 Excellent : congestion = low,    density optimal  → 75–100
    Tier 3 Good      : congestion = low,    density high     → 50– 74
                     : congestion = medium, density optimal  → 50– 74
    Tier 2 Poor      : congestion = medium, others          → 25– 49
    Tier 1 Bad       : congestion = high                    → 0 – 24
    """
    if congestion == "high":
        # Bad: 0–24 — clamp density to reasonable range
        d = float(np.clip(local_density, 0, 2))
        return int(np.interp(d, [0, 2], [0, 24]))
    if congestion == "medium":
        d = float(np.clip(local_density, 0, 20))
        return int(np.interp(d, [0, 20], [25, 49]))
    # low congestion
    if local_density <= 10:
        return int(np.interp(float(np.clip(local_density, 2, 10)), [2, 10], [75, 100]))
    # over-built but low congestion → still good
    d = float(np.clip(local_density, 10, 30))
    return int(np.interp(d, [10, 30], [74, 50]))


def grid_from_traffic(geojson_path):
    """
    Re-score a traffic analysis grid GeoJSON produced by traffic_analysis.py.

    The input already has per-cell congestion labels and local_density values.
    This function re-applies scoring and returns a clean grid GeoJSON compatible
    with the standard grid tab rendering.
    """
    import json
    with open(geojson_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    cell_size_m = data.get("cell_size_m", 0)
    features    = []

    for feat in data.get("features", []):
        props      = feat.get("properties", {})
        service    = props.get("service", "traffic")
        if service != "traffic":
            continue  # skip hotspot features if combined file is passed

        congestion     = props.get("congestion", "low")
        local_density  = props.get("local_density", 0.0) or 0.0
        local_pressure = props.get("local_pressure")

        score = _score_traffic(local_density, congestion)

        out_props = {
            "value":          round(float(local_density), 4),
            "qol_score":      score,
            "congestion":     congestion,
            "road_length_km": props.get("road_length_km"),
            "service":        "traffic",
        }
        if local_pressure is not None:
            out_props["local_pressure"] = local_pressure

        features.append({
            "type":       feat["type"],
            "geometry":   feat["geometry"],
            "properties": out_props,
        })

    return {
        "type":        "FeatureCollection",
        "features":    features,
        "cell_size_m": cell_size_m,
    }


def _score_informal_settlement(irregularity_score):
    """
    Irregularity score (0=planned, 100=informal) → QoL score (0=bad, 100=good).

    Tier 4 Excellent (QoL 75–100): irregularity  0–15  (very planned)
    Tier 3 Good      (QoL 50– 74): irregularity 16–33
    Tier 2 Poor      (QoL 25– 49): irregularity 34–66
    Tier 1 Bad       (QoL  0– 24): irregularity 67–100 (informal)
    """
    if irregularity_score is None or (isinstance(irregularity_score, float) and np.isnan(irregularity_score)):
        return None
    s = int(np.clip(irregularity_score, 0, 100))
    if s <= 15:
        return int(np.interp(s, [0,  15],  [100, 75]))
    if s <= 33:
        return int(np.interp(s, [15, 33],  [74,  50]))
    if s <= 66:
        return int(np.interp(s, [33, 66],  [49,  25]))
    return int(np.interp(s, [66, 100], [24,  0]))


def grid_from_informal_settlement(geojson_path):
    """
    Re-score an informal settlement analysis GeoJSON produced by
    informal_settlement.py.  Skips high_irregularity_zone features.
    Returns a clean grid GeoJSON compatible with the standard grid tab.
    """
    import json
    with open(geojson_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    cell_size_m = data.get("cell_size_m", 0)
    features    = []

    for feat in data.get("features", []):
        props = feat.get("properties", {})
        if props.get("type") == "high_irregularity_zone":
            continue

        irr   = props.get("irregularity_score")
        score = _score_informal_settlement(irr) if irr is not None else None
        label = props.get("classification", "unknown")

        features.append({
            "type":     feat["type"],
            "geometry": feat["geometry"],
            "properties": {
                "value":               irr,
                "qol_score":           score,
                "classification":      label,
                "texture_val":         props.get("texture_val"),
                "edge_val":            props.get("edge_val"),
                "buildup_ratio":       props.get("buildup_ratio"),
                "cell_cx":             props.get("cell_cx"),
                "cell_cy":             props.get("cell_cy"),
                "service":             "informal-settlement",
            },
        })

    return {
        "type":        "FeatureCollection",
        "features":    features,
        "cell_size_m": cell_size_m,
    }


def grid_from_vegetation(geojson_path):
    """
    Re-score a vegetation density cell GeoJSON produced by vegetation_density.py.

    The input already has per-cell vegetation_pct values — this function
    re-applies the scoring function and returns a clean grid GeoJSON
    compatible with the standard grid tab rendering.
    """
    import json
    with open(geojson_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    cell_size_m = data.get("cell_size_m", 0)
    features    = []

    for feat in data.get("features", []):
        props   = feat.get("properties", {})
        veg_pct = props.get("vegetation_pct")
        score   = _score_vegetation_pct(veg_pct) if veg_pct is not None else None

        features.append({
            "type":     feat["type"],
            "geometry": feat["geometry"],
            "properties": {
                "value":        round(float(veg_pct), 2) if veg_pct is not None else None,
                "qol_score":    score,
                "passes_30pct": props.get("passes_30pct"),
                "cell_cx":      props.get("cell_cx"),
                "cell_cy":      props.get("cell_cy"),
                "service":      "vegetation",
            },
        })

    return {
        "type":        "FeatureCollection",
        "features":    features,
        "cell_size_m": cell_size_m,
    }


# ── Expansion: combine multiple grids into a weighted composite ───────────────

def combine_grids_weighted(grids_with_weights: list) -> dict:
    """
    Combine multiple QoL grid GeoJSONs into a single weighted composite grid.

    Parameters
    ----------
    grids_with_weights : list of (geojson_dict, weight) tuples
        Weights are normalised internally so they don't need to sum to 1.

    Returns
    -------
    dict — FeatureCollection with weighted_score / qol_score (0-100).
    """
    if not grids_with_weights:
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    total_weight = sum(w for _, w in grids_with_weights)
    if total_weight == 0:
        total_weight = 1.0
    norm_weights = [w / total_weight for _, w in grids_with_weights]
    grids        = [g for g, _ in grids_with_weights]

    # Union bounding box of all source grids
    all_minx = all_miny = float("inf")
    all_maxx = all_maxy = float("-inf")
    for gj in grids:
        for feat in gj.get("features", []):
            geom = feat.get("geometry", {})
            if geom.get("type") == "Polygon":
                coords = geom["coordinates"][0]
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                all_minx = min(all_minx, min(xs))
                all_miny = min(all_miny, min(ys))
                all_maxx = max(all_maxx, max(xs))
                all_maxy = max(all_maxy, max(ys))

    if all_minx == float("inf"):
        return {"type": "FeatureCollection", "features": [], "cell_size_m": 0}

    union_bounds = (all_minx, all_miny, all_maxx, all_maxy)
    common_gdf, cell_size_m = _build_grid_cells(union_bounds)

    # Build centroid lookup arrays per source grid for fast nearest-cell matching
    layer_lookups = []
    for gj in grids:
        cx_arr, cy_arr, score_arr = [], [], []
        for feat in gj.get("features", []):
            p     = feat.get("properties", {})
            score = p.get("qol_score")
            if score is None:
                continue
            geom = feat.get("geometry", {})
            if geom.get("type") == "Polygon":
                coords = geom["coordinates"][0]
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                cx_arr.append((min(xs) + max(xs)) / 2)
                cy_arr.append((min(ys) + max(ys)) / 2)
                score_arr.append(float(score))
        if cx_arr:
            layer_lookups.append((np.array(cx_arr), np.array(cy_arr), np.array(score_arr)))
        else:
            layer_lookups.append(None)

    # Search radius: 2× the largest source cell size converted to degrees
    max_source_cell_m = max((gj.get("cell_size_m") or cell_size_m) for gj in grids)
    search_deg = (max_source_cell_m * 2) / 111_000

    features = []
    for _, row in common_gdf.iterrows():
        geom = row.geometry
        cx   = geom.centroid.x
        cy   = geom.centroid.y

        weighted_sum   = 0.0
        covered_weight = 0.0
        layer_scores   = []

        for i, lookup in enumerate(layer_lookups):
            if lookup is None:
                layer_scores.append(None)
                continue
            cx_arr, cy_arr, score_arr = lookup
            dists       = np.sqrt((cx_arr - cx) ** 2 + (cy_arr - cy) ** 2)
            nearest_idx = int(np.argmin(dists))
            if dists[nearest_idx] <= search_deg:
                sc = score_arr[nearest_idx]
                weighted_sum   += norm_weights[i] * sc
                covered_weight += norm_weights[i]
                layer_scores.append(round(float(sc), 1))
            else:
                layer_scores.append(None)

        if covered_weight < 0.01:
            continue

        final_score = round(weighted_sum / covered_weight)
        final_score = max(0, min(100, final_score))

        features.append({
            "type": "Feature",
            "geometry": geom.__geo_interface__,
            "properties": {
                "weighted_score": final_score,
                "qol_score":      final_score,
                "layer_scores":   layer_scores,
            },
        })

    return {
        "type":        "FeatureCollection",
        "features":    features,
        "cell_size_m": cell_size_m,
    }


def extract_top_areas(weighted_grid: dict, top_n: int = 3) -> list:
    """
    Return top N contiguous high-scoring clusters, ranked best to least.
    Minimum cluster size scales with the total grid size (3% of cells).
    Boundary is the tight union of actual cell polygons — no convex hull.
    """
    from shapely.geometry import shape

    features = weighted_grid.get("features", [])
    if not features:
        return []

    total_cells   = len(features)
    cell_size_m   = weighted_grid.get("cell_size_m", 200)
    cell_size_deg = cell_size_m / 111_000 * 1.5          # adjacency radius
    cell_buf_deg  = (cell_size_m / 2) / 111_000           # half-cell buffer

    scores    = np.array([f["properties"].get("weighted_score", 0) for f in features])
    score_min = float(scores.min())
    score_max = float(scores.max())
    score_range = score_max - score_min

    # Minimum cluster size: 3% of total cells, at least 2
    size_frac     = 0.03
    abs_min_cells = max(2, int(total_cells * size_frac))

    # ── helpers ────────────────────────────────────────────────────────────────

    def build_clusters(high_feats):
        geoms  = [shape(f["geometry"]) for f in high_feats]
        s_arr  = [f["properties"].get("weighted_score", 0) for f in high_feats]
        ls_arr = [f["properties"].get("layer_scores", []) for f in high_feats]
        n      = len(geoms)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        cents = [(g.centroid.x, g.centroid.y) for g in geoms]
        for i in range(n):
            for j in range(i + 1, n):
                dx = cents[i][0] - cents[j][0]
                dy = cents[i][1] - cents[j][1]
                if (dx*dx + dy*dy) ** 0.5 <= cell_size_deg:
                    parent[find(i)] = find(j)

        groups: dict = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)
        return groups, geoms, s_arr, ls_arr

    def cavg(idxs, s_arr):
        return sum(s_arr[i] for i in idxs) / len(idxs)

    def layer_avgs(idxs, ls_arr):
        if not ls_arr or not ls_arr[idxs[0]]:
            return []
        num_layers = len(ls_arr[idxs[0]])
        result = []
        for li in range(num_layers):
            vals = [ls_arr[i][li] for i in idxs if ls_arr[i] and ls_arr[i][li] is not None]
            result.append(round(sum(vals)/len(vals), 1) if vals else None)
        return result

    def tight_boundary(cluster_geoms):
        """Actual cell union with a small buffer-unbuffer to close gaps."""
        merged = unary_union(cluster_geoms)
        merged = merged.buffer(cell_buf_deg * 0.6).buffer(-cell_buf_deg * 0.4)
        if merged.is_empty:
            merged = unary_union(cluster_geoms)
        return merged

    def make_entry(idxs, geoms, s_arr, ls_arr):
        boundary = tight_boundary([geoms[i] for i in idxs])
        c = boundary.centroid
        return {
            "boundary":         boundary.__geo_interface__,
            "score":            round(cavg(idxs, s_arr), 1),
            "cell_count":       len(idxs),
            "centroid":         [round(c.x, 6), round(c.y, 6)],
            "layer_avg_scores": layer_avgs(idxs, ls_arr),
        }

    # ── adaptive threshold loop ────────────────────────────────────────────────
    # Strategy:
    #   • Walk thresholds from 90th pct down to 55th in 5-pt steps.
    #   • At each step collect ALL clusters that pass abs_min_cells (size filter).
    #   • Skip if the largest single cluster swallows >50% of high cells (blob).
    #   • Skip if threshold is not meaningfully above the score floor.
    #   • Track the candidate set that yields the MOST clusters passing size filter.
    #   • Also track the candidate set with the MOST clusters regardless of count,
    #     so we can fill up to top_n even if no single threshold gives top_n.
    #   • Never break early — exhaust all thresholds so lower ones (larger clusters)
    #     are considered when size=large, higher ones (more clusters) for size=small.

    # Score each threshold attempt and pick the best trade-off:
    #   primary key  = number of eligible clusters (want top_n)
    #   secondary key = how well cluster sizes match the requested size_frac
    candidates_by_pct = []  # list of (n_eligible, result_list)

    for pct in range(90, 50, -5):
        threshold = float(np.percentile(scores, pct))

        # Skip degenerate thresholds (≤ 5% above score floor)
        if score_range > 0 and (threshold - score_min) < score_range * 0.05:
            continue

        high_feats = [f for f in features
                      if (f["properties"].get("weighted_score") or 0) >= threshold]
        n_high = len(high_feats)

        if n_high < abs_min_cells:
            continue

        groups, geoms, s_arr, ls_arr = build_clusters(high_feats)

        # Blob guard: skip if one cluster eats more than half the high-scoring cells
        largest = max(len(v) for v in groups.values())
        if largest > n_high * 0.50:
            continue

        eligible = [idxs for idxs in groups.values() if len(idxs) >= abs_min_cells]
        if not eligible:
            continue

        ranked = sorted(eligible, key=lambda idx: cavg(idx, s_arr), reverse=True)[:top_n]
        result = [make_entry(idxs, geoms, s_arr, ls_arr) for idxs in ranked]
        candidates_by_pct.append((len(result), result))

    if candidates_by_pct:
        # Pick the attempt with the most clusters; on a tie take the one with
        # the highest total cell count (larger, more meaningful zones).
        best_result = max(candidates_by_pct,
                          key=lambda item: (item[0], sum(r["cell_count"] for r in item[1])))[1]
    else:
        best_result = []

    # Last-resort: no threshold passed the blob guard (highly uniform data).
    # Take the tightest high-scoring cluster we can find, no blob check.
    if not best_result:
        for pct in range(90, 20, -5):
            threshold = float(np.percentile(scores, pct))
            if score_range > 0 and (threshold - score_min) < score_range * 0.02:
                continue
            high_feats = [f for f in features
                          if (f["properties"].get("weighted_score") or 0) >= threshold]
            if len(high_feats) < abs_min_cells:
                continue
            groups, geoms, s_arr, ls_arr = build_clusters(high_feats)
            # Apply size filter even in last resort
            eligible = [idxs for idxs in groups.values() if len(idxs) >= abs_min_cells]
            if not eligible:
                continue
            ranked = sorted(eligible, key=lambda idx: cavg(idx, s_arr), reverse=True)[:top_n]
            best_result = [make_entry(idxs, geoms, s_arr, ls_arr) for idxs in ranked]
            if best_result:
                break

    return best_result
