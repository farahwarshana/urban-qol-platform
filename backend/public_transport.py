"""
public_transport.py
Transit coverage analysis using simple geometric buffer operations.

Steps
-----
1. Buffer each station by walking_distance_m (default 1000 m).
2. Merge buffers into a single union polygon.
3. Intersect merged coverage with the AOI to get covered area.
4. Calculate area-based coverage percentage.
5. Subtract covered area from AOI to get uncovered polygons.
6. Optionally calculate population coverage percentage from a polygon layer.
"""

import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
from scipy.spatial.distance import cdist


def _get_utm_epsg(lon, lat):
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def calculate_transit_coverage(
    stations_geojson_path: str,
    aoi_geojson_path: str,
    walking_distance_m: float = 1000.0,
    population_geojson_path: str = None,
    population_field: str = None,
    output_path: str = None,
):
    """
    Calculate public-transit walking coverage within an AOI.

    Parameters
    ----------
    stations_geojson_path : str
        GeoJSON point layer of transit stations.
    aoi_geojson_path : str
        GeoJSON polygon defining the area of interest.
    walking_distance_m : float
        Buffer radius in metres (default 1 000 m).
    population_geojson_path : str, optional
        GeoJSON polygon layer with population attribute.
    population_field : str, optional
        Attribute name holding population counts.
    output_path : str, optional
        Where to write the coverage GeoJSON (uncovered areas).

    Returns
    -------
    dict with keys:
        coverage_pct        float  - % of AOI area covered
        uncovered_geojson   dict   - GeoJSON FeatureCollection of uncovered polygons
        covered_geojson     dict   - GeoJSON FeatureCollection of covered area
        population_pct      float | None
        overall_score       float  - 0-100
        station_count       int
        walking_distance_m  float
    """
    # ── Load inputs ──────────────────────────────────────────────────────────
    stations = gpd.read_file(stations_geojson_path)
    aoi      = gpd.read_file(aoi_geojson_path)

    if stations.crs is None:
        stations = stations.set_crs("EPSG:4326")
    if aoi.crs is None:
        aoi = aoi.set_crs("EPSG:4326")

    stations = stations.to_crs("EPSG:4326")
    aoi      = aoi.to_crs("EPSG:4326")

    if len(stations) == 0:
        raise ValueError("Stations GeoJSON contains no features.")
    if len(aoi) == 0:
        raise ValueError("AOI GeoJSON contains no features.")

    # Keep only point geometries
    stations = stations[stations.geometry.geom_type.isin(["Point", "MultiPoint"])]
    if len(stations) == 0:
        raise ValueError("No Point geometries found in stations layer.")

    # ── Project to UTM for accurate buffering ────────────────────────────────
    centroid  = aoi.geometry.union_all().centroid
    utm_epsg  = _get_utm_epsg(centroid.x, centroid.y)
    utm_crs   = f"EPSG:{utm_epsg}"

    stations_utm = stations.to_crs(utm_crs)
    aoi_utm      = aoi.to_crs(utm_crs)

    aoi_union_utm = unary_union(aoi_utm.geometry)

    # ── Buffer stations and merge ─────────────────────────────────────────────
    buffers_utm   = stations_utm.geometry.buffer(walking_distance_m)
    coverage_utm  = unary_union(buffers_utm)

    # ── Clip coverage to AOI ─────────────────────────────────────────────────
    covered_utm   = coverage_utm.intersection(aoi_union_utm)

    # ── Area-based coverage % ────────────────────────────────────────────────
    aoi_area_m2     = aoi_union_utm.area
    covered_area_m2 = covered_utm.area if not covered_utm.is_empty else 0.0
    coverage_pct    = (covered_area_m2 / aoi_area_m2 * 100.0) if aoi_area_m2 > 0 else 0.0

    # ── Uncovered area ───────────────────────────────────────────────────────
    uncovered_utm = aoi_union_utm.difference(covered_utm)

    # ── Convert results back to WGS84 ────────────────────────────────────────
    def _geom_to_wgs(geom):
        if geom is None or geom.is_empty:
            return None
        gdf_tmp = gpd.GeoDataFrame(geometry=[geom], crs=utm_crs)
        return gdf_tmp.to_crs("EPSG:4326").geometry.iloc[0]

    covered_wgs   = _geom_to_wgs(covered_utm)
    uncovered_wgs = _geom_to_wgs(uncovered_utm)

    # ── Build output GeoDataFrames ───────────────────────────────────────────
    def _explode_to_features(geom, props):
        """Split multi-polygon into individual features for clean GeoJSON."""
        if geom is None or geom.is_empty:
            return []
        gdf_tmp = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
        gdf_tmp = gdf_tmp.explode(index_parts=False).reset_index(drop=True)
        features = []
        for _, row in gdf_tmp.iterrows():
            features.append({
                "type": "Feature",
                "geometry": row.geometry.__geo_interface__,
                "properties": dict(props),
            })
        return features

    covered_features   = _explode_to_features(covered_wgs,   {"type": "covered"})
    uncovered_features = _explode_to_features(uncovered_wgs, {"type": "uncovered"})

    covered_geojson   = {"type": "FeatureCollection", "features": covered_features}
    uncovered_geojson = {"type": "FeatureCollection", "features": uncovered_features}

    # ── Station distribution stats ───────────────────────────────────────────
    station_distribution = "N/A"
    avg_station_distance_m = None
    gap_regions = []

    if len(stations_utm) >= 2:
        coords = np.array([(geom.x, geom.y) for geom in stations_utm.geometry])
        dists = cdist(coords, coords)

        # Avg distance between stations: mean of all unique pairwise distances
        upper = dists[np.triu_indices(len(coords), k=1)]
        avg_station_distance_m = round(float(upper.mean()), 1)

        # Clark-Evans index: observed avg nearest-neighbour vs random expectation
        # R < 1 → clustered, R >= 1 → spread/uniform
        np.fill_diagonal(dists, np.inf)
        nearest_dists = dists.min(axis=1)
        avg_nearest_obs = float(nearest_dists.mean())
        aoi_area_for_dist = aoi_union_utm.area
        n = len(coords)
        expected_nearest = 0.5 * np.sqrt(aoi_area_for_dist / n) if n > 0 else 1
        clark_evans_r = avg_nearest_obs / expected_nearest if expected_nearest > 0 else 1
        station_distribution = "Spread" if clark_evans_r >= 1.0 else "Clustered"

    # ── Gap region detection ─────────────────────────────────────────────────
    if uncovered_wgs is not None and not uncovered_wgs.is_empty:
        from shapely.geometry import mapping
        gdf_unc = gpd.GeoDataFrame(geometry=[uncovered_wgs], crs="EPSG:4326")
        gdf_unc = gdf_unc.explode(index_parts=False).reset_index(drop=True)
        aoi_total_area = aoi_union_utm.area
        threshold_frac = 0.10  # flag zones covering >10% of AOI
        for _, row in gdf_unc.iterrows():
            geom_wgs = row.geometry
            geom_utm = gpd.GeoDataFrame(geometry=[geom_wgs], crs="EPSG:4326").to_crs(utm_crs).geometry.iloc[0]
            frac = geom_utm.area / aoi_total_area if aoi_total_area > 0 else 0
            if frac >= threshold_frac:
                centroid_wgs = geom_wgs.centroid
                gap_regions.append({
                    "lat": round(centroid_wgs.y, 4),
                    "lon": round(centroid_wgs.x, 4),
                    "area_pct": round(frac * 100, 1),
                })

    # ── Optional population coverage ─────────────────────────────────────────
    population_pct = None
    if population_geojson_path and population_field:
        try:
            pop_gdf = gpd.read_file(population_geojson_path)
            if pop_gdf.crs is None:
                pop_gdf = pop_gdf.set_crs("EPSG:4326")
            pop_gdf = pop_gdf.to_crs(utm_crs)

            if population_field not in pop_gdf.columns:
                raise ValueError(f"Population field '{population_field}' not found.")

            pop_gdf["_pop"] = pop_gdf[population_field].fillna(0).astype(float)
            pop_gdf["_area_utm"] = pop_gdf.geometry.area

            total_pop = 0.0
            covered_pop = 0.0

            for _, row in pop_gdf.iterrows():
                poly = row.geometry
                pop  = row["_pop"]
                area = row["_area_utm"]
                if area <= 0 or pop <= 0:
                    continue
                total_pop += pop
                intersection = poly.intersection(covered_utm)
                if not intersection.is_empty:
                    frac = intersection.area / area
                    covered_pop += pop * frac

            if total_pop > 0:
                population_pct = covered_pop / total_pop * 100.0
        except Exception as pop_err:
            # Non-fatal: return None and let caller decide
            population_pct = None

    # ── Overall score (0–100) ────────────────────────────────────────────────
    # Weighted: 70% area coverage + 30% population coverage (if available)
    if population_pct is not None:
        overall_score = 0.7 * coverage_pct + 0.3 * population_pct
    else:
        overall_score = coverage_pct

    overall_score = round(min(max(overall_score, 0.0), 100.0), 2)

    # ── Save output if requested ─────────────────────────────────────────────
    if output_path:
        # Save full coverage result (covered + uncovered) with a type attribute
        all_features = covered_features + uncovered_features
        all_geojson  = {"type": "FeatureCollection", "features": all_features}
        import json
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(all_geojson, fh)

    return {
        "coverage_pct":            round(coverage_pct, 2),
        "uncovered_geojson":       uncovered_geojson,
        "covered_geojson":         covered_geojson,
        "population_pct":          round(population_pct, 2) if population_pct is not None else None,
        "overall_score":           overall_score,
        "station_count":           len(stations),
        "walking_distance_m":      walking_distance_m,
        "station_distribution":    station_distribution,
        "avg_station_distance_m":  avg_station_distance_m,
        "gap_regions":             gap_regions,
        "stations_geojson":        stations.to_crs("EPSG:4326").__geo_interface__,
        "aoi_geojson":             aoi.to_crs("EPSG:4326").__geo_interface__,
    }
