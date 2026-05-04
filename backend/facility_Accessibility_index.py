import os
import geopandas as gpd
import osmnx as ox
import networkx as nx
import pandas as pd


def calculate_facility_accessibility(
    facilities_geojson_path,
    output_dir,
    facility_id=0,
    walking_speed_kmh=4.5,
    times_minutes=[5, 10, 15],
    network_dist_m=2000
):
    os.makedirs(output_dir, exist_ok=True)

    facilities = gpd.read_file(facilities_geojson_path)

    if facilities.crs is None:
        facilities = facilities.set_crs("EPSG:4326")

    facilities = facilities.to_crs("EPSG:4326")

    selected = facilities.iloc[facility_id]
    facility_geom = selected.geometry

    if facility_geom.geom_type != "Point":
        facility_geom = facility_geom.centroid

    lat = facility_geom.y
    lon = facility_geom.x

    print("Downloading walking network from OSM...")

    G = ox.graph_from_point(
        (lat, lon),
        dist=network_dist_m,
        network_type="walk",
        simplify=True
    )

    G = ox.project_graph(G)
    nodes, edges = ox.graph_to_gdfs(G)

    facility_point_proj = gpd.GeoSeries(
        [facility_geom],
        crs="EPSG:4326"
    ).to_crs(nodes.crs).iloc[0]

    nearest_node = nodes.geometry.distance(facility_point_proj).idxmin()

    meters_per_minute = (walking_speed_kmh * 1000) / 60

    output_files = []
    zones = []

    for time in times_minutes:
        max_distance = meters_per_minute * time

        reached = nx.single_source_dijkstra_path_length(
            G,
            nearest_node,
            cutoff=max_distance,
            weight="length"
        )

        reached_nodes = list(reached.keys())
        reached_points = nodes.loc[reached_nodes]

        if len(reached_points) < 3:
            continue

        polygon = reached_points.geometry.unary_union.convex_hull

        zone_gdf = gpd.GeoDataFrame(
            {
                "facility_id": [int(facility_id)],
                "time_min": [time],
                "distance_m": [round(max_distance, 2)],
                "walking_speed_kmh": [walking_speed_kmh],
                "category": [f"within_{time}_min"]
            },
            geometry=[polygon],
            crs=nodes.crs
        ).to_crs("EPSG:4326")

        out_file = os.path.join(
            output_dir,
            f"facility_access_{time}min.geojson"
        )

        zone_gdf.to_file(out_file, driver="GeoJSON")

        output_files.append(out_file)
        zones.append(zone_gdf)

    if not zones:
        raise ValueError("No accessibility zones could be created.")

    all_zones = gpd.GeoDataFrame(
        pd.concat(zones, ignore_index=True),
        crs="EPSG:4326"
    )

    all_output = os.path.join(
        output_dir,
        "facility_accessibility_zones.geojson"
    )

    all_zones.to_file(all_output, driver="GeoJSON")

    return {
        "indicator": "Facility Accessibility Index",
        "facility_id": int(facility_id),
        "selected_lat": lat,
        "selected_lon": lon,
        "walking_speed_kmh": walking_speed_kmh,
        "time_zones_minutes": times_minutes,
        "outputs": output_files,
        "combined_output": all_output
    }