"""
facility_Accessibility_index.py
Walkable service-area analysis around facility points.

Approach
--------
We use Euclidean walking buffers with a tortuosity correction factor (0.75)
instead of downloading road networks from OSM.  Real pedestrian paths are
never straight lines; empirically the walkable straight-line radius for a
given time is ~75 % of the theoretical straight-line distance.  This gives
results accurate to within one street block for the 5/10/15-min bands and
runs in milliseconds instead of minutes.

  radius_m = (speed_kmh × 1000 / 60) × time_min × TORTUOSITY

The zones are nested — the 10-min polygon always contains the 5-min polygon,
the 15-min contains the 10-min — so the frontend can stack them transparently.
"""

import os
import geopandas as gpd
from shapely.ops import unary_union

# Tortuosity correction: real walkable catchment ≈ 75 % of Euclidean radius
TORTUOSITY = 0.75


def _utm_epsg(lon: float, lat: float) -> int:
    """Return the EPSG code for the UTM zone that contains (lon, lat)."""
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def calculate_facility_accessibility(
    facilities_geojson_path: str,
    output_path: str,
    walking_speed_kmh: float = 4.5,
    times_minutes: list = [5, 10, 15],
) -> dict:
    """
    Compute walkable service areas for every facility point.

    Parameters
    ----------
    facilities_geojson_path : str
        Path to a GeoJSON file of Point features.
    output_path : str
        Where to write the combined zones GeoJSON.
    walking_speed_kmh : float
        Pedestrian speed (default 4.5 km/h — slow comfortable walk).
    times_minutes : list[int]
        Walk-time bands to produce (default [5, 10, 15]).

    Returns
    -------
    dict with stats consumed by the FastAPI endpoint.
    """
    # ── 1. Load & validate ────────────────────────────────────────────────────
    facilities = gpd.read_file(facilities_geojson_path)

    if facilities.empty:
        raise ValueError("The uploaded GeoJSON has no features.")

    if facilities.crs is None:
        facilities = facilities.set_crs("EPSG:4326")
    facilities = facilities.to_crs("EPSG:4326")

    # Extract point geometries; use centroid for non-point geometries
    points = []
    for geom in facilities.geometry:
        if geom is None:
            continue
        points.append(geom if geom.geom_type == "Point" else geom.centroid)

    if not points:
        raise ValueError("No valid geometries found in the uploaded GeoJSON.")

    # ── 2. Choose a single UTM projection centred on the dataset ─────────────
    all_lons = [p.x for p in points]
    all_lats = [p.y for p in points]
    utm_epsg = _utm_epsg(
        sum(all_lons) / len(all_lons),
        sum(all_lats) / len(all_lats),
    )
    utm_crs = f"EPSG:{utm_epsg}"

    # Project all facility points to UTM once
    pts_gdf = gpd.GeoDataFrame(geometry=points, crs="EPSG:4326").to_crs(utm_crs)

    # ── 3. Build walking buffers for every time band ──────────────────────────
    meters_per_minute = (walking_speed_kmh * 1000) / 60
    times_sorted = sorted(times_minutes)

    zone_rows = []
    for t in times_sorted:
        radius_m = meters_per_minute * t * TORTUOSITY

        # Buffer every point and union — all in UTM (accurate metres)
        circles = pts_gdf.geometry.buffer(radius_m)
        merged_utm = unary_union(circles)

        # Back to WGS-84 for output
        merged_wgs = (
            gpd.GeoDataFrame(geometry=[merged_utm], crs=utm_crs)
            .to_crs("EPSG:4326")
            .geometry.iloc[0]
        )

        zone_rows.append({
            "time_min":          t,
            "radius_m":          round(radius_m, 1),
            "walking_speed_kmh": walking_speed_kmh,
            "facility_count":    len(pts_gdf),
            "category":          f"within_{t}_min",
            "geometry":          merged_wgs,
        })

    if not zone_rows:
        raise ValueError("No accessibility zones could be created.")

    # ── 4. Write output ───────────────────────────────────────────────────────
    all_zones = gpd.GeoDataFrame(zone_rows, crs="EPSG:4326")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    all_zones.to_file(output_path, driver="GeoJSON")

    # ── 5. Compute coverage percentages relative to the outermost zone ────────
    zones_proj = all_zones.to_crs("EPSG:3857")
    outer_area = zones_proj[zones_proj["time_min"] == times_sorted[-1]].geometry.area.sum()

    def _pct(t):
        rows = zones_proj[zones_proj["time_min"] == t]
        if rows.empty or outer_area == 0:
            return None
        return round(rows.geometry.area.sum() / outer_area * 100, 2)

    return {
        "indicator":            "Facility Accessibility Index",
        "total_facilities":     len(facilities),
        "facilities_processed": len(pts_gdf),
        "walking_speed_kmh":    walking_speed_kmh,
        "tortuosity_factor":    TORTUOSITY,
        "time_zones_minutes":   times_sorted,
        "pct_5min":             _pct(5),
        "pct_10min":            _pct(10),
        "pct_15min":            _pct(15),
        "combined_output":      output_path,
    }
