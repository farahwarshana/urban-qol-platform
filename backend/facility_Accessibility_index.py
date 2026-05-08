import os
import geopandas as gpd
import osmnx as ox
import networkx as nx
import pandas as pd
from shapely.ops import unary_union


def calculate_facility_accessibility(
    facilities_geojson_path,
    output_path,
    walking_speed_kmh=4.5,
    times_minutes=[5, 10, 15],
    network_dist_m=2000
):
    facilities = gpd.read_file(facilities_geojson_path)

    if facilities.crs is None:
        facilities = facilities.set_crs("EPSG:4326")
    facilities = facilities.to_crs("EPSG:4326")

    meters_per_minute = (walking_speed_kmh * 1000) / 60

    # Collect isochrone polygons per time band across every facility point
    time_polygons = {t: [] for t in times_minutes}
    processed = 0

    for idx, row in facilities.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        if geom.geom_type != "Point":
            geom = geom.centroid

        lat, lon = geom.y, geom.x

        print(f"  Facility {idx}: network from ({lat:.5f}, {lon:.5f})…")

        try:
            G = ox.graph_from_point(
                (lat, lon),
                dist=network_dist_m,
                network_type="walk",
                simplify=True
            )
        except Exception as e:
            print(f"    Skipping facility {idx}: {e}")
            continue

        G = ox.project_graph(G)
        nodes, _ = ox.graph_to_gdfs(G)

        pt_proj = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(nodes.crs).iloc[0]
        nearest = nodes.geometry.distance(pt_proj).idxmin()

        for t in times_minutes:
            reached = nx.single_source_dijkstra_path_length(
                G, nearest, cutoff=meters_per_minute * t, weight="length"
            )
            pts = nodes.loc[list(reached.keys())]
            if len(pts) < 3:
                continue
            poly_proj = pts.geometry.unary_union.convex_hull
            poly_wgs = gpd.GeoDataFrame(geometry=[poly_proj], crs=nodes.crs).to_crs("EPSG:4326").geometry.iloc[0]
            time_polygons[t].append(poly_wgs)

        processed += 1

    if processed == 0:
        raise ValueError("No facility points could be processed — check your GeoJSON and network distance.")

    zones = []
    for t in times_minutes:
        polys = time_polygons[t]
        if not polys:
            continue
        merged = unary_union(polys)
        zones.append(gpd.GeoDataFrame(
            {
                "time_min":         [t],
                "distance_m":       [round(meters_per_minute * t, 2)],
                "walking_speed_kmh":[walking_speed_kmh],
                "facility_count":   [len(polys)],
                "category":         [f"within_{t}_min"],
            },
            geometry=[merged],
            crs="EPSG:4326"
        ))

    if not zones:
        raise ValueError("No accessibility zones could be created.")

    all_zones = gpd.GeoDataFrame(pd.concat(zones, ignore_index=True), crs="EPSG:4326")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    all_zones.to_file(output_path, driver="GeoJSON")

    # Compute area-based coverage percentages
    all_proj = all_zones.to_crs("EPSG:3857")
    total_area = all_proj[all_proj["time_min"] == max(times_minutes)].geometry.area.sum()

    def _pct(t):
        rows = all_proj[all_proj["time_min"] == t]
        if rows.empty or total_area == 0:
            return None
        return round(rows.geometry.area.sum() / total_area * 100, 2)

    return {
        "indicator":           "Facility Accessibility Index",
        "total_facilities":    len(facilities),
        "facilities_processed": processed,
        "walking_speed_kmh":   walking_speed_kmh,
        "network_dist_m":      network_dist_m,
        "time_zones_minutes":  times_minutes,
        "pct_5min":            _pct(5),
        "pct_10min":           _pct(10),
        "pct_15min":           _pct(15),
        "combined_output":     output_path,
    }
