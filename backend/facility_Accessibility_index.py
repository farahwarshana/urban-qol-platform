"""
facility_Accessibility_index.py
Walkable service-area analysis around facility points.

Approach
--------
Euclidean walking buffers with a tortuosity correction factor (0.75).
Real pedestrian paths are never straight lines; the walkable straight-line
radius for a given time is ~75 % of the theoretical straight-line distance.

  radius_m = (speed_kmh × 1000 / 60) × time_min × TORTUOSITY

When an AOI boundary is supplied the zones are clipped to it and an
uncovered layer (AOI minus outermost zone) is added to the output.
Zones are nested — each larger band fully contains all smaller bands.
"""

import os
import json
import geopandas as gpd
from shapely.ops import unary_union

TORTUOSITY = 0.75


def _utm_epsg(lon: float, lat: float) -> int:
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def _explode_to_features(geom, props: dict) -> list:
    """Split a (multi-)polygon into individual GeoJSON Feature dicts."""
    if geom is None or geom.is_empty:
        return []
    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    return [
        {"type": "Feature", "geometry": row.geometry.__geo_interface__, "properties": dict(props)}
        for _, row in gdf.iterrows()
    ]


def calculate_facility_accessibility(
    facilities_geojson_path: str,
    output_path: str,
    walking_speed_kmh: float = 4.5,
    times_minutes: list = [5, 10, 15],
    aoi_geojson_path: str = None,
) -> dict:
    """
    Compute walkable service areas for every facility point.

    Parameters
    ----------
    facilities_geojson_path : str
        GeoJSON file of Point features.
    output_path : str
        Where to write the combined zones GeoJSON.
    walking_speed_kmh : float
        Pedestrian speed in km/h (default 4.5).
    times_minutes : list[int]
        Walk-time bands to produce (default [5, 10, 15]).
    aoi_geojson_path : str, optional
        GeoJSON polygon defining the area of interest.  When provided:
        - zones are clipped to the AOI
        - an uncovered layer (AOI − outermost zone) is appended
        - coverage % is computed relative to the AOI area

    Returns
    -------
    dict consumed by the FastAPI endpoint.
    """
    # ── 1. Load & validate facilities ────────────────────────────────────────
    facilities = gpd.read_file(facilities_geojson_path)
    if facilities.empty:
        raise ValueError("The uploaded GeoJSON has no features.")
    if facilities.crs is None:
        facilities = facilities.set_crs("EPSG:4326")
    facilities = facilities.to_crs("EPSG:4326")

    points = []
    for geom in facilities.geometry:
        if geom is None:
            continue
        points.append(geom if geom.geom_type == "Point" else geom.centroid)
    if not points:
        raise ValueError("No valid geometries found in the uploaded GeoJSON.")

    # ── 2. Optional AOI ───────────────────────────────────────────────────────
    aoi_union_wgs = None
    aoi_gdf = None
    if aoi_geojson_path:
        aoi_gdf = gpd.read_file(aoi_geojson_path)
        if aoi_gdf.crs is None:
            aoi_gdf = aoi_gdf.set_crs("EPSG:4326")
        aoi_gdf = aoi_gdf.to_crs("EPSG:4326")
        if aoi_gdf.empty:
            raise ValueError("AOI GeoJSON contains no features.")
        aoi_union_wgs = unary_union(aoi_gdf.geometry)

    # ── 3. Choose UTM projection centred on the dataset ───────────────────────
    all_lons = [p.x for p in points]
    all_lats = [p.y for p in points]
    utm_epsg = _utm_epsg(sum(all_lons) / len(all_lons), sum(all_lats) / len(all_lats))
    utm_crs  = f"EPSG:{utm_epsg}"

    pts_gdf = gpd.GeoDataFrame(geometry=points, crs="EPSG:4326").to_crs(utm_crs)

    aoi_union_utm = None
    if aoi_union_wgs is not None:
        aoi_union_utm = (
            gpd.GeoDataFrame(geometry=[aoi_union_wgs], crs="EPSG:4326")
            .to_crs(utm_crs)
            .geometry.iloc[0]
        )

    # ── 4. Build walking buffers for every time band ──────────────────────────
    meters_per_minute = (walking_speed_kmh * 1000) / 60
    times_sorted = sorted(times_minutes)

    zone_features = []       # GeoJSON features for zone polygons
    zone_geoms_utm = {}      # time → merged UTM geometry (for coverage calc)

    for t in times_sorted:
        radius_m   = meters_per_minute * t * TORTUOSITY
        circles    = pts_gdf.geometry.buffer(radius_m)
        merged_utm = unary_union(circles)

        # Clip to AOI if provided
        if aoi_union_utm is not None:
            merged_utm = merged_utm.intersection(aoi_union_utm)

        zone_geoms_utm[t] = merged_utm

        merged_wgs = (
            gpd.GeoDataFrame(geometry=[merged_utm], crs=utm_crs)
            .to_crs("EPSG:4326")
            .geometry.iloc[0]
        )

        zone_features += _explode_to_features(merged_wgs, {
            "type":              "zone",
            "time_min":          t,
            "radius_m":          round(radius_m, 1),
            "walking_speed_kmh": walking_speed_kmh,
            "facility_count":    len(pts_gdf),
            "category":          f"within_{t}_min",
        })

    if not zone_features:
        raise ValueError("No accessibility zones could be created.")

    # ── 5. Covered / uncovered split (only when AOI is provided) ─────────────
    coverage_pct  = None
    uncovered_pct = None
    has_aoi       = aoi_union_utm is not None

    if has_aoi:
        aoi_area_m2      = aoi_union_utm.area
        outermost_utm    = zone_geoms_utm[times_sorted[-1]]
        covered_area_m2  = outermost_utm.area if not outermost_utm.is_empty else 0.0
        coverage_pct     = round(covered_area_m2 / aoi_area_m2 * 100.0, 2) if aoi_area_m2 > 0 else 0.0
        uncovered_pct    = round(100.0 - coverage_pct, 2)

        uncovered_utm = aoi_union_utm.difference(outermost_utm)
        uncovered_wgs = (
            gpd.GeoDataFrame(geometry=[uncovered_utm], crs=utm_crs)
            .to_crs("EPSG:4326")
            .geometry.iloc[0]
        ) if not uncovered_utm.is_empty else None

        zone_features += _explode_to_features(uncovered_wgs, {
            "type":     "uncovered",
            "time_min": None,
            "category": "uncovered",
        })

        # Add AOI boundary outline feature
        aoi_wgs = (
            gpd.GeoDataFrame(geometry=[aoi_union_wgs], crs="EPSG:4326")
            .geometry.iloc[0]
        )
        zone_features += _explode_to_features(aoi_wgs, {"layer": "boundary"})

    # ── 6. Write combined GeoJSON ─────────────────────────────────────────────
    geojson_out = {"type": "FeatureCollection", "features": zone_features}
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(geojson_out, fh)

    # ── 7. Coverage percentages per zone ─────────────────────────────────────
    # Relative to AOI area (if provided) or outermost zone area (fallback)
    if has_aoi:
        ref_area_m2 = aoi_union_utm.area
    else:
        outermost_geom = zone_geoms_utm[times_sorted[-1]]
        ref_area_m2    = outermost_geom.area if not outermost_geom.is_empty else 1.0

    zone_pcts = {}
    for t in times_sorted:
        geom = zone_geoms_utm[t]
        zone_pcts[str(t)] = (
            round(geom.area / ref_area_m2 * 100.0, 2)
            if (geom and not geom.is_empty and ref_area_m2 > 0)
            else None
        )

    return {
        "indicator":            "Facility Accessibility Index",
        "total_facilities":     len(facilities),
        "facilities_processed": len(pts_gdf),
        "walking_speed_kmh":    walking_speed_kmh,
        "tortuosity_factor":    TORTUOSITY,
        "time_zones_minutes":   times_sorted,
        "zone_pcts":            zone_pcts,
        "has_aoi":              has_aoi,
        "coverage_pct":         coverage_pct,
        "uncovered_pct":        uncovered_pct,
        "combined_output":      output_path,
    }
