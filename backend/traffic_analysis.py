"""
traffic_analysis.py
Road network structural analysis and congestion detection using geometric operations only.

Full-area analysis
------------------
1. Classify each road segment by hierarchy using length + connectivity:
   - Primary   : long segments (top 20%) OR high intersection degree (≥ 4 connections)
   - Secondary : medium segments OR moderate connectivity (3 connections)
   - Local     : short / fragmented segments
2. Compute structural network metrics:
   - Total road length, intersection density, connectivity index, avg segment length
3. Identify main corridors (primary roads), dense intersections, fragmented zones.

Grid / congestion analysis
--------------------------
4. Build a uniform grid over the AOI (clipped to boundary).
5. Per cell: local road density + optional local traffic pressure.
6. Classify each cell: low / medium / high congestion.
7. Merge high-congestion cells into hotspot polygons.
"""

import json
import math
import numpy as np
import geopandas as gpd
from collections import defaultdict
from shapely.geometry import box, mapping, Point
from shapely.ops import unary_union, split


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


# ── Road hierarchy thresholds (percentile-based, computed per dataset) ────────
# Primary   : length ≥ P80  OR  node degree ≥ 4
# Secondary : length ≥ P40  OR  node degree == 3
# Local     : everything else


def _snap_coord(x, y, precision=5):
    """Round coordinate to snap nearby endpoints into the same node."""
    return (round(x, precision), round(y, precision))


def _build_node_degree(segments_utm):
    """
    Count how many segments touch each endpoint node.
    Returns dict: snapped_coord → degree (int).
    """
    degree = defaultdict(int)
    for geom in segments_utm:
        coords = list(geom.coords) if geom.geom_type == "LineString" else []
        if geom.geom_type == "MultiLineString":
            for part in geom.geoms:
                coords = list(part.coords)
                if len(coords) >= 2:
                    degree[_snap_coord(*coords[0])]  += 1
                    degree[_snap_coord(*coords[-1])] += 1
            continue
        if len(coords) >= 2:
            degree[_snap_coord(*coords[0])]  += 1
            degree[_snap_coord(*coords[-1])] += 1
    return degree


def _segment_max_degree(geom, degree_map):
    """Return the maximum node degree at either endpoint of a segment."""
    if geom.geom_type == "LineString":
        coords = list(geom.coords)
    elif geom.geom_type == "MultiLineString":
        coords = list(geom.geoms[0].coords)
    else:
        return 1
    if len(coords) < 2:
        return 1
    d0 = degree_map.get(_snap_coord(*coords[0]),  1)
    d1 = degree_map.get(_snap_coord(*coords[-1]), 1)
    return max(d0, d1)


def analyse_road_network(roads_clipped_utm, aoi_union_utm, utm_crs):
    """
    Classify roads by hierarchy and compute structural network metrics.

    Parameters
    ----------
    roads_clipped_utm : GeoDataFrame  — road segments clipped to AOI, in UTM CRS
    aoi_union_utm     : shapely geom  — AOI polygon in UTM CRS
    utm_crs           : str           — e.g. "EPSG:32636"

    Returns
    -------
    dict with keys:
        network_geojson     dict   — GeoJSON FeatureCollection with hierarchy property
        total_length_km     float
        segment_count       int
        avg_segment_len_m   float
        intersection_density float  — intersections per km²
        connectivity_index  float   — avg node degree (higher = better connected)
        primary_pct         float
        secondary_pct       float
        local_pct           float
        primary_length_km   float
        secondary_length_km float
        local_length_km     float
        fragmented_zone_pct float   — % of AOI where only local roads exist
    """
    if roads_clipped_utm.empty:
        empty = {"type": "FeatureCollection", "features": []}
        return {
            "network_geojson": empty,
            "total_length_km": 0, "segment_count": 0,
            "avg_segment_len_m": 0, "intersection_density": 0,
            "connectivity_index": 0,
            "primary_pct": 0, "secondary_pct": 0, "local_pct": 100,
            "primary_length_km": 0, "secondary_length_km": 0, "local_length_km": 0,
            "fragmented_zone_pct": 0,
        }

    lengths_m  = roads_clipped_utm.geometry.length.values
    total_len_m = lengths_m.sum()
    total_len_km = total_len_m / 1_000.0
    avg_len_m    = float(np.mean(lengths_m)) if len(lengths_m) else 0.0

    # ── Length percentile thresholds ─────────────────────────────────────────
    p80 = float(np.percentile(lengths_m, 80))
    p40 = float(np.percentile(lengths_m, 40))

    # ── Node degree map ───────────────────────────────────────────────────────
    degree_map = _build_node_degree(roads_clipped_utm.geometry)

    # Count true intersections (nodes with degree ≥ 3)
    intersections = [c for c, d in degree_map.items() if d >= 3]
    aoi_area_km2  = aoi_union_utm.area / 1_000_000.0
    int_density   = len(intersections) / aoi_area_km2 if aoi_area_km2 > 0 else 0.0

    all_degrees   = list(degree_map.values())
    conn_index    = float(np.mean(all_degrees)) if all_degrees else 0.0

    # ── Classify each segment ─────────────────────────────────────────────────
    hierarchies  = []
    for i, (_, row) in enumerate(roads_clipped_utm.iterrows()):
        geom   = row.geometry
        length = lengths_m[i]
        deg    = _segment_max_degree(geom, degree_map)

        if length >= p80 or deg >= 4:
            h = "primary"
        elif length >= p40 or deg == 3:
            h = "secondary"
        else:
            h = "local"
        hierarchies.append(h)

    roads_clipped_utm = roads_clipped_utm.copy()
    roads_clipped_utm["hierarchy"] = hierarchies
    roads_clipped_utm["length_m"]  = lengths_m
    roads_clipped_utm["max_degree"] = [
        _segment_max_degree(g, degree_map) for g in roads_clipped_utm.geometry
    ]

    # ── Length by hierarchy ───────────────────────────────────────────────────
    primary_len_km   = roads_clipped_utm.loc[roads_clipped_utm["hierarchy"] == "primary",   "length_m"].sum() / 1000
    secondary_len_km = roads_clipped_utm.loc[roads_clipped_utm["hierarchy"] == "secondary", "length_m"].sum() / 1000
    local_len_km     = roads_clipped_utm.loc[roads_clipped_utm["hierarchy"] == "local",     "length_m"].sum() / 1000

    n = len(hierarchies)
    primary_pct   = hierarchies.count("primary")   / n * 100 if n else 0
    secondary_pct = hierarchies.count("secondary") / n * 100 if n else 0
    local_pct     = hierarchies.count("local")     / n * 100 if n else 0

    # ── Convert back to WGS84 for GeoJSON output ──────────────────────────────
    roads_wgs = roads_clipped_utm.to_crs("EPSG:4326")

    features = []
    for _, row in roads_wgs.iterrows():
        geom = row.geometry
        features.append({
            "type": "Feature",
            "geometry": geom.__geo_interface__,
            "properties": {
                "hierarchy":  row["hierarchy"],
                "length_m":   round(float(row["length_m"]), 1),
                "max_degree": int(row["max_degree"]),
                "service":    "traffic-network",
            },
        })

    network_geojson = {"type": "FeatureCollection", "features": features}

    # ── Fragmented zone estimate ──────────────────────────────────────────────
    # Approximate: buffer local-only roads, measure non-primary/secondary coverage
    if not roads_clipped_utm.empty:
        local_only = roads_clipped_utm[roads_clipped_utm["hierarchy"] == "local"]
        higher     = roads_clipped_utm[roads_clipped_utm["hierarchy"].isin(["primary", "secondary"])]
        if not higher.empty and not local_only.empty:
            higher_buf = unary_union(higher.geometry.buffer(200))  # 200 m influence radius
            local_geoms = unary_union(local_only.geometry.buffer(100))
            frag_zone   = local_geoms.difference(higher_buf).intersection(aoi_union_utm)
            frag_pct    = frag_zone.area / aoi_union_utm.area * 100 if aoi_union_utm.area > 0 else 0.0
        else:
            frag_pct = local_pct  # all local → fully fragmented
    else:
        frag_pct = 0.0

    return {
        "network_geojson":      network_geojson,
        "total_length_km":      round(total_len_km, 3),
        "segment_count":        n,
        "avg_segment_len_m":    round(avg_len_m, 1),
        "intersection_density": round(int_density, 2),
        "connectivity_index":   round(conn_index, 2),
        "primary_pct":          round(primary_pct, 1),
        "secondary_pct":        round(secondary_pct, 1),
        "local_pct":            round(local_pct, 1),
        "primary_length_km":    round(primary_len_km, 3),
        "secondary_length_km":  round(secondary_len_km, 3),
        "local_length_km":      round(local_len_km, 3),
        "fragmented_zone_pct":  round(frag_pct, 1),
    }


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
        network              dict   - structural analysis results (hierarchy, metrics)
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

    # ── Road network structural analysis ────────────────────────────────────
    network = analyse_road_network(roads_clipped_utm, aoi_union_utm, utm_crs)

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

        # Clip cell strictly to AOI — this is the only geometry we output
        cell_in_aoi = cell_geom.intersection(aoi_union_utm)
        if cell_in_aoi.is_empty:
            continue
        effective_area_m2  = cell_in_aoi.area
        effective_area_km2 = effective_area_m2 / 1_000_000.0

        # Measure road length only within the AOI-clipped cell shape
        if roads_union_utm is not None and not roads_union_utm.is_empty:
            road_in_cell    = roads_union_utm.intersection(cell_in_aoi)
            cell_road_len_m = road_in_cell.length if not road_in_cell.is_empty else 0.0
        else:
            cell_road_len_m = 0.0

        cell_road_len_km = cell_road_len_m / 1_000.0
        local_density    = (cell_road_len_km / effective_area_km2) if effective_area_km2 > 0 else 0.0

        # Local traffic pressure
        local_pressure = None
        if population is not None and cell_road_len_km > 0 and aoi_area_km2 > 0:
            area_fraction  = effective_area_m2 / aoi_area_m2
            local_pop      = population * area_fraction
            local_pressure = local_pop / cell_road_len_km

        congestion = _classify_congestion(local_density, local_pressure)

        # Reproject clipped cell shape (not the raw grid square) to WGS84 for output
        cell_in_aoi_wgs = (
            gpd.GeoDataFrame(geometry=[cell_in_aoi], crs=utm_crs)
            .to_crs("EPSG:4326")
            .geometry.iloc[0]
        )

        props = {
            "road_length_km": round(cell_road_len_km, 4),
            "local_density":  round(local_density, 4),
            "congestion":     congestion,
            "service":        "traffic",
        }
        if local_pressure is not None:
            props["local_pressure"] = round(local_pressure, 2)

        grid_features.append({
            "type":       "Feature",
            "geometry":   mapping(cell_in_aoi_wgs),
            "properties": props,
        })

        if congestion == "high":
            hotspot_polys.append(cell_in_aoi_wgs)

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
        "network":            network,
        "grid_geojson":       grid_geojson,
        "hotspots_geojson":   hotspots_geojson,
        "high_congestion_pct": round(high_congestion_pct, 2),
        "cell_size_m":        cell_m,
    }
