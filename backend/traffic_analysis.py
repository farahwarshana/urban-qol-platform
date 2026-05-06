"""
traffic_analysis.py
Road network analysis and congestion detection using geometric operations only.

Steps
-----
1. Clip road network to AOI and calculate total road length (km).
2. Compute road density (km of road per km² of AOI).
3. Classify density: Low / Optimal / High.
4. If population provided, estimate traffic pressure (pop / road_km).
5. Build a uniform grid over the AOI.
6. Per cell: local road density + optional local traffic pressure.
7. Classify each cell as low / medium / high congestion.
8. Identify high-congestion hotspots and dissolve into polygons.
"""

import json
import math
import numpy as np
import geopandas as gpd
from shapely.geometry import box, mapping
from shapely.ops import unary_union


# ── Constants ─────────────────────────────────────────────────────────────────

# Road density thresholds (km of road per km² of area)
_DENSITY_LOW_THRESHOLD     = 2.0   # < 2 km/km²  → Low (underdeveloped)
_DENSITY_HIGH_THRESHOLD    = 10.0  # > 10 km/km² → High (overbuilt)

# Traffic pressure thresholds (people per km of road)
_PRESSURE_LOW_THRESHOLD    = 500
_PRESSURE_HIGH_THRESHOLD   = 2000

# Grid target cell count (shared with other services)
_GRID_TARGET_CELLS = 400
_CELL_MIN_M        = 50


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_utm_epsg(lon, lat):
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def _adaptive_cell_size(bounds_4326):
    """Derive a clean cell size so that cols × rows ≈ _GRID_TARGET_CELLS."""
    minx, miny, maxx, maxy = bounds_4326
    cy = (miny + maxy) / 2
    lat_rad  = math.radians(cy)
    width_m  = abs(maxx - minx) * 111_000 * math.cos(lat_rad)
    height_m = abs(maxy - miny) * 111_000

    raw = (width_m * height_m / _GRID_TARGET_CELLS) ** 0.5

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


def _build_grid(bounds_4326):
    """Return (GeoDataFrame of WGS84 cells, cell_size_m)."""
    minx, miny, maxx, maxy = bounds_4326
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    cell_m   = _adaptive_cell_size(bounds_4326)
    utm_epsg = _get_utm_epsg(cx, cy)
    utm_crs  = f"EPSG:{utm_epsg}"

    corners_gdf = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy([minx, maxx], [miny, maxy]),
        crs="EPSG:4326",
    ).to_crs(utm_crs)
    x0, y0 = corners_gdf.geometry.iloc[0].x, corners_gdf.geometry.iloc[0].y
    x1, y1 = corners_gdf.geometry.iloc[1].x, corners_gdf.geometry.iloc[1].y

    xs = np.arange(x0, x1, cell_m)
    ys = np.arange(y0, y1, cell_m)

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


def _classify_density(density_km_per_km2):
    """Classify road density into Low / Optimal / High."""
    if density_km_per_km2 < _DENSITY_LOW_THRESHOLD:
        return "low"
    if density_km_per_km2 > _DENSITY_HIGH_THRESHOLD:
        return "high"
    return "optimal"


def _classify_congestion(local_density, local_pressure=None):
    """
    Classify a cell's congestion level based on density and optional pressure.

    Returns: "low", "medium", or "high"
    """
    density_level = _classify_density(local_density)

    if local_pressure is not None:
        if local_pressure > _PRESSURE_HIGH_THRESHOLD or density_level == "low":
            # High pressure on low-density roads → high congestion risk
            if local_pressure > _PRESSURE_HIGH_THRESHOLD and density_level in ("low", "optimal"):
                return "high"
            if local_pressure > _PRESSURE_LOW_THRESHOLD and density_level == "low":
                return "high"
            if local_pressure > _PRESSURE_HIGH_THRESHOLD:
                return "high"
            if local_pressure > _PRESSURE_LOW_THRESHOLD:
                return "medium"
            return "low"
        if density_level == "high":
            return "medium"
        return "low"

    # Density-only classification
    if density_level == "low":
        return "high"    # insufficient roads → congestion risk
    if density_level == "optimal":
        return "low"
    return "medium"      # overbuilt can still have flow issues


# ── Main Analysis ─────────────────────────────────────────────────────────────

def calculate_traffic_analysis(
    roads_geojson_path: str,
    aoi_geojson_path: str,
    population: float = None,
    output_path: str = None,
):
    """
    Analyse road network density and traffic congestion within an AOI.

    Parameters
    ----------
    roads_geojson_path : str
        GeoJSON LineString layer of road network.
    aoi_geojson_path : str
        GeoJSON polygon defining the area of interest.
    population : float, optional
        Total population within the AOI (used to estimate traffic pressure).
    output_path : str, optional
        Where to write the combined output GeoJSON.

    Returns
    -------
    dict with keys:
        road_length_km       float  - total road length inside AOI
        aoi_area_km2         float  - AOI area in km²
        road_density         float  - km of road per km²
        density_class        str    - "low" / "optimal" / "high"
        traffic_pressure     float | None  - people per road-km
        grid_geojson         dict   - FeatureCollection (cells with congestion)
        hotspots_geojson     dict   - FeatureCollection (merged high-congestion polygons)
        high_congestion_pct  float  - % of AOI area classified as high congestion
        cell_size_m          int
    """
    # ── Load inputs ──────────────────────────────────────────────────────────
    roads = gpd.read_file(roads_geojson_path)
    aoi   = gpd.read_file(aoi_geojson_path)

    if roads.crs is None:
        roads = roads.set_crs("EPSG:4326")
    if aoi.crs is None:
        aoi = aoi.set_crs("EPSG:4326")

    roads = roads.to_crs("EPSG:4326")
    aoi   = aoi.to_crs("EPSG:4326")

    if len(roads) == 0:
        raise ValueError("Roads GeoJSON contains no features.")
    if len(aoi) == 0:
        raise ValueError("AOI GeoJSON contains no features.")

    # Keep only LineString geometries
    roads = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    if len(roads) == 0:
        raise ValueError("No LineString geometries found in roads layer.")

    # ── Project to UTM for accurate measurements ─────────────────────────────
    aoi_union_4326 = unary_union(aoi.geometry)
    centroid       = aoi_union_4326.centroid
    utm_epsg       = _get_utm_epsg(centroid.x, centroid.y)
    utm_crs        = f"EPSG:{utm_epsg}"

    roads_utm = roads.to_crs(utm_crs)
    aoi_utm   = aoi.to_crs(utm_crs)
    aoi_union_utm = unary_union(aoi_utm.geometry)

    # ── Clip roads to AOI ────────────────────────────────────────────────────
    roads_clipped_utm = roads_utm.copy()
    roads_clipped_utm["geometry"] = roads_utm.geometry.intersection(aoi_union_utm)
    roads_clipped_utm = roads_clipped_utm[~roads_clipped_utm.geometry.is_empty]
    roads_clipped_utm = roads_clipped_utm[
        roads_clipped_utm.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ]

    # ── Overall stats ────────────────────────────────────────────────────────
    total_length_m  = roads_clipped_utm.geometry.length.sum()
    total_length_km = total_length_m / 1_000.0

    aoi_area_m2  = aoi_union_utm.area
    aoi_area_km2 = aoi_area_m2 / 1_000_000.0

    road_density    = (total_length_km / aoi_area_km2) if aoi_area_km2 > 0 else 0.0
    density_class   = _classify_density(road_density)

    traffic_pressure = None
    if population is not None and total_length_km > 0:
        traffic_pressure = population / total_length_km

    # ── Build grid ───────────────────────────────────────────────────────────
    bounds     = aoi_union_4326.bounds  # (minx, miny, maxx, maxy)
    grid, cell_m = _build_grid(bounds)

    # Clip grid cells to AOI outline
    grid_utm       = grid.to_crs(utm_crs)
    roads_union_utm = unary_union(roads_clipped_utm.geometry) if len(roads_clipped_utm) > 0 else None

    grid_features  = []
    hotspot_polys  = []

    for idx, row in grid_utm.iterrows():
        cell_geom = row.geometry
        cell_area_m2 = cell_geom.area

        # Check cell overlaps AOI
        if not cell_geom.intersects(aoi_union_utm):
            continue

        # Clip cell to AOI
        cell_in_aoi = cell_geom.intersection(aoi_union_utm)
        if cell_in_aoi.is_empty:
            continue
        effective_area_m2 = cell_in_aoi.area
        effective_area_km2 = effective_area_m2 / 1_000_000.0

        # Measure road length in this cell
        if roads_union_utm is not None and not roads_union_utm.is_empty:
            road_in_cell = roads_union_utm.intersection(cell_geom)
            cell_road_len_m  = road_in_cell.length if not road_in_cell.is_empty else 0.0
        else:
            cell_road_len_m = 0.0

        cell_road_len_km  = cell_road_len_m / 1_000.0
        local_density     = (cell_road_len_km / effective_area_km2) if effective_area_km2 > 0 else 0.0

        # Local traffic pressure
        local_pressure = None
        if population is not None and cell_road_len_km > 0 and aoi_area_km2 > 0:
            # Distribute population proportionally by cell area fraction
            area_fraction  = effective_area_m2 / aoi_area_m2
            local_pop      = population * area_fraction
            local_pressure = local_pop / cell_road_len_km

        congestion = _classify_congestion(local_density, local_pressure)

        # Convert cell back to WGS84 for output
        cell_wgs = grid.loc[idx].geometry

        props = {
            "road_length_km":  round(cell_road_len_km, 4),
            "local_density":   round(local_density, 4),
            "congestion":      congestion,
            "service":         "traffic",
        }
        if local_pressure is not None:
            props["local_pressure"] = round(local_pressure, 2)

        grid_features.append({
            "type":       "Feature",
            "geometry":   mapping(cell_wgs),
            "properties": props,
        })

        if congestion == "high":
            hotspot_polys.append(cell_wgs)

    # ── Merge hotspot polygons ───────────────────────────────────────────────
    if hotspot_polys:
        merged = unary_union(hotspot_polys)
        hotspot_gdf = gpd.GeoDataFrame(geometry=[merged], crs="EPSG:4326").explode(index_parts=False)
        hotspot_features = []
        for _, hr in hotspot_gdf.iterrows():
            hotspot_features.append({
                "type":       "Feature",
                "geometry":   hr.geometry.__geo_interface__,
                "properties": {"type": "hotspot"},
            })
    else:
        hotspot_features = []

    hotspots_geojson = {"type": "FeatureCollection", "features": hotspot_features}

    # ── Summary stats ────────────────────────────────────────────────────────
    total_cells = len(grid_features)
    high_cells  = sum(1 for f in grid_features if f["properties"]["congestion"] == "high")
    high_congestion_pct = (high_cells / total_cells * 100.0) if total_cells > 0 else 0.0

    grid_geojson = {
        "type":         "FeatureCollection",
        "features":     grid_features,
        "cell_size_m":  cell_m,
    }

    # ── Save output ──────────────────────────────────────────────────────────
    if output_path:
        combined = {
            "type": "FeatureCollection",
            "features": grid_features + hotspot_features,
            "cell_size_m": cell_m,
        }
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(combined, fh)

    return {
        "road_length_km":     round(total_length_km, 3),
        "aoi_area_km2":       round(aoi_area_km2, 3),
        "road_density":       round(road_density, 4),
        "density_class":      density_class,
        "traffic_pressure":   round(traffic_pressure, 2) if traffic_pressure is not None else None,
        "grid_geojson":       grid_geojson,
        "hotspots_geojson":   hotspots_geojson,
        "high_congestion_pct": round(high_congestion_pct, 2),
        "cell_size_m":        cell_m,
    }
