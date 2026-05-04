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


def _build_grid_cells(bounds_4326, cell_m=200):
    """
    Given a bounding box in WGS84 degrees, return a GeoDataFrame of
    200 m × 200 m cells in EPSG:4326.

    Parameters
    ----------
    bounds_4326 : (minx, miny, maxx, maxy)  in degrees
    cell_m      : cell size in metres (default 200)

    Returns
    -------
    GeoDataFrame with polygon geometry column, CRS = EPSG:4326
    """
    minx, miny, maxx, maxy = bounds_4326
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

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
            # corners in UTM
            corners_utm = [
                (xi,          yi),
                (xi + cell_m, yi),
                (xi + cell_m, yi + cell_m),
                (xi,          yi + cell_m),
            ]
            # back to WGS84
            corners_wgs = [to_wgs84.transform(cx, cy) for cx, cy in corners_utm]
            cells.append(box(
                min(p[0] for p in corners_wgs),
                min(p[1] for p in corners_wgs),
                max(p[0] for p in corners_wgs),
                max(p[1] for p in corners_wgs),
            ))

    gdf = gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")
    return gdf


# ── Scoring functions ─────────────────────────────────────────────────────────

def _score_ndvi(value):
    """NDVI -1..1 → QoL score 0..100."""
    if np.isnan(value) or value <= -0.1:
        return None
    if value < 0.0:
        return int(np.interp(value, [-0.1, 0.0], [0, 10]))
    if value < 0.2:
        return int(np.interp(value, [0.0, 0.2], [10, 40]))
    if value < 0.5:
        return int(np.interp(value, [0.2, 0.5], [40, 70]))
    return int(np.interp(value, [0.5, 1.0], [70, 100]))


def _score_heat_index(cls_value):
    """Heat index class 0-3 → QoL score."""
    mapping = {0: 100, 1: 65, 2: 30, 3: 5}
    if np.isnan(cls_value) or cls_value < 0:
        return None
    return mapping.get(int(round(cls_value)), None)


def _score_crime(density):
    """Crime density (crimes/km²) → QoL score (lower density = better)."""
    if np.isnan(density) or density < 0:
        return None
    score = max(0.0, 100.0 - (density / 50.0) * 100.0)
    return int(round(score))


def _score_urban_density(density):
    """Population/km² → QoL score (moderate density is ideal)."""
    if np.isnan(density) or density < 0:
        return None
    if density < 100:
        return int(np.interp(density, [0, 100], [30, 40]))
    if density < 500:
        return int(np.interp(density, [100, 500], [40, 70]))
    if density < 2000:
        return int(np.interp(density, [500, 2000], [70, 100]))
    if density < 5000:
        return int(np.interp(density, [2000, 5000], [100, 40]))
    return int(np.interp(min(density, 15000), [5000, 15000], [40, 10]))


def _score_facility_accessibility(walk_time_min):
    """Walk-time in minutes → QoL score."""
    if walk_time_min is None:
        return 0
    if walk_time_min <= 5:
        return 100
    if walk_time_min <= 10:
        return 65
    if walk_time_min <= 15:
        return 35
    return 0


# ── Per-service grid builders ─────────────────────────────────────────────────

def grid_from_raster(raster_path, service_type, cell_m=200):
    """
    Sample a single-band GeoTIFF on a 200 m grid and return a GeoJSON-serialisable dict.

    Parameters
    ----------
    raster_path  : path to the GeoTIFF (EPSG:4326)
    service_type : "ndvi" | "heat-index"
    cell_m       : cell size in metres

    Returns
    -------
    dict  — GeoJSON FeatureCollection
    """
    score_fn = _score_ndvi if service_type == "ndvi" else _score_heat_index

    with rasterio.open(raster_path) as src:
        bounds = src.bounds          # left, bottom, right, top
        nodata = src.nodata if src.nodata is not None else -9999
        data   = src.read(1).astype("float32")
        transform = src.transform
        crs_epsg = src.crs.to_epsg() if src.crs else 4326

    # If not already 4326 we can't simply read lat/lng — reprojection needed.
    # The heat_index backend already outputs 4326; ndvi may vary.
    # We re-open and reproject if necessary so our grid sampling stays simple.
    bounds_4326 = (bounds.left, bounds.bottom, bounds.right, bounds.top)

    grid = _build_grid_cells(bounds_4326, cell_m)

    features = []
    for _, row in grid.iterrows():
        geom = row.geometry
        cx = geom.centroid.x
        cy = geom.centroid.y

        # Convert centroid to pixel row/col
        try:
            col, r = ~transform * (cx, cy)
            col, r = int(col), int(r)
            h, w = data.shape
            if 0 <= r < h and 0 <= col < w:
                val = float(data[r, col])
                if val == nodata or (service_type == "ndvi" and val == -9999):
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
                "value": round(val, 4) if not np.isnan(val) else None,
                "qol_score": score,
                "service": service_type,
            }
        })

    return {"type": "FeatureCollection", "features": features}


def grid_from_vector(geojson_path, service_type, value_field, cell_m=200):
    """
    Overlay a 200 m grid on a polygon GeoJSON, inherit the value of the
    containing polygon per cell, and score each cell.

    Parameters
    ----------
    geojson_path  : path to result GeoJSON (crime or urban density output)
    service_type  : "crime" | "urban-density"
    value_field   : field name carrying the numeric value (e.g. 'crime_density')
    cell_m        : cell size in metres

    Returns
    -------
    dict — GeoJSON FeatureCollection
    """
    score_fn = _score_crime if service_type == "crime" else _score_urban_density

    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    bounds = gdf.total_bounds   # minx, miny, maxx, maxy
    grid   = _build_grid_cells(tuple(bounds), cell_m)

    # Spatial join: each cell gets the value of the polygon it intersects most
    joined = gpd.sjoin(grid, gdf[[value_field, "geometry"]], how="left", predicate="intersects")

    # If multiple polygons match, take the mean
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
                "value": round(float(val), 4) if not (isinstance(val, float) and np.isnan(val)) else None,
                "qol_score": score,
                "service": service_type,
            }
        })

    return {"type": "FeatureCollection", "features": features}


def grid_from_facility_accessibility(geojson_path, cell_m=200):
    """
    Score cells based on the minimum walk time from a facility accessibility
    isochrone GeoJSON.  The isochrone GeoJSON contains zones for 5, 10, 15 min.
    Cells outside all zones get score 0.
    """
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")

    bounds = gdf.total_bounds
    grid   = _build_grid_cells(tuple(bounds), cell_m)

    # Walk-time column names in facility accessibility output
    time_col = None
    for candidate in ["walk_time", "time_min", "minutes", "travel_time"]:
        if candidate in gdf.columns:
            time_col = candidate
            break

    features = []
    for _, row in grid.iterrows():
        geom = row.geometry
        centroid = geom.centroid
        pt = gpd.GeoDataFrame(geometry=[centroid], crs="EPSG:4326")

        joined = gpd.sjoin(pt, gdf, how="left", predicate="within")

        if time_col and not joined.empty and time_col in joined.columns:
            times = joined[time_col].dropna()
            walk_time = float(times.min()) if len(times) > 0 else None
        else:
            # fallback: use zone ordering by area (smallest = closest)
            if not joined.empty and len(joined) > 0:
                walk_time = 5  # if inside any zone, assume closest
            else:
                walk_time = None

        score = _score_facility_accessibility(walk_time)

        features.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "value": walk_time,
                "qol_score": score,
                "service": "facility-accessibility",
            }
        })

    return {"type": "FeatureCollection", "features": features}
