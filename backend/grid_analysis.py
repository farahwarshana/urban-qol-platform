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


def grid_from_facility_accessibility(geojson_path):
    """
    Score cells based on the minimum walk time from a facility accessibility
    isochrone GeoJSON (zones for 5/10/15 min).
    Only cells whose centroid falls inside an isochrone zone are kept —
    cells outside all zones are outside the analysis boundary and are dropped.
    Cell size is chosen automatically based on extent (target ~600 cells max).
    """
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    bounds       = gdf.total_bounds
    grid, cell_m = _build_grid_cells(tuple(bounds))

    # Boundary filter: keep only cells whose centroid is inside the data bbox
    minx, miny, maxx, maxy = bounds
    centroids = grid.geometry.centroid
    in_bounds = (
        (centroids.x >= minx) & (centroids.x <= maxx) &
        (centroids.y >= miny) & (centroids.y <= maxy)
    )
    grid = grid[in_bounds].copy()

    time_col = None
    for candidate in ["walk_time", "time_min", "minutes", "travel_time"]:
        if candidate in gdf.columns:
            time_col = candidate
            break

    # Vectorised sjoin: centroid within isochrone polygon
    centroids_gdf = gpd.GeoDataFrame(
        geometry=grid.geometry.centroid.values,
        index=grid.index,
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(centroids_gdf, gdf, how="left", predicate="within")

    features = []
    for idx, row in grid.iterrows():
        matches = joined.loc[[idx]] if idx in joined.index else joined.iloc[0:0]

        if matches.empty or matches["index_right"].isna().all():
            # Centroid outside all isochrone zones — outside analysis extent, skip
            continue

        if time_col and time_col in matches.columns:
            times     = matches[time_col].dropna()
            walk_time = float(times.min()) if len(times) > 0 else None
        else:
            walk_time = 5  # inside a zone but no time column — assume closest

        score = _score_facility_accessibility(walk_time)

        features.append({
            "type": "Feature",
            "geometry": mapping(row.geometry),
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
