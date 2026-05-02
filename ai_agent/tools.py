import os

import geopandas as gpd
from shapely.geometry import Point


def _ensure_file_exists(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Grid file not found: {path}")


def _get_id_column(gdf: gpd.GeoDataFrame) -> str:
    if "cell_id" in gdf.columns:
        return "cell_id"
    if "grid_id" in gdf.columns:
        return "grid_id"
    raise ValueError("Grid file is missing required column: cell_id or grid_id")


def _prepare_output_path(output_path: str) -> None:
    folder = os.path.dirname(output_path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def create_vegetation_zone(cell_id, grid_path, output_path):
    _ensure_file_exists(grid_path)
    gdf = gpd.read_file(grid_path)
    id_column = _get_id_column(gdf)

    selected = gdf[gdf[id_column] == cell_id]
    if selected.empty:
        raise ValueError(f"Cell not found: {cell_id}")

    geometry = selected.geometry.iloc[0]
    buffered = geometry.buffer(-10)
    if buffered.is_empty:
        geometry = geometry
    else:
        geometry = buffered

    result_gdf = gpd.GeoDataFrame(
        [{
            "cell_id": cell_id,
            "recommendation": "vegetation_zone",
            "geometry": geometry,
        }],
        geometry="geometry",
        crs=gdf.crs,
    )

    _prepare_output_path(output_path)
    result_gdf.to_file(output_path, driver="GeoJSON")

    return {
        "status": "created",
        "output_path": output_path,
        "cell_id": cell_id,
    }


def create_cool_roof_zone(cell_id, grid_path, output_path):
    _ensure_file_exists(grid_path)
    gdf = gpd.read_file(grid_path)
    id_column = _get_id_column(gdf)

    selected = gdf[gdf[id_column] == cell_id]
    if selected.empty:
        raise ValueError(f"Cell not found: {cell_id}")

    result_gdf = gpd.GeoDataFrame(
        [{
            "cell_id": cell_id,
            "recommendation": "cool_roofs",
            "geometry": selected.geometry.iloc[0],
        }],
        geometry="geometry",
        crs=gdf.crs,
    )

    _prepare_output_path(output_path)
    result_gdf.to_file(output_path, driver="GeoJSON")

    return {
        "status": "created",
        "output_path": output_path,
        "cell_id": cell_id,
    }


def create_shading_zone(cell_id, grid_path, output_path):
    _ensure_file_exists(grid_path)
    gdf = gpd.read_file(grid_path)
    id_column = _get_id_column(gdf)

    selected = gdf[gdf[id_column] == cell_id]
    if selected.empty:
        raise ValueError(f"Cell not found: {cell_id}")

    geometry = selected.geometry.iloc[0]
    centroid = geometry.centroid
    shading_geometry = centroid.buffer(30)

    result_gdf = gpd.GeoDataFrame(
        [{
            "cell_id": cell_id,
            "recommendation": "shading",
            "geometry": shading_geometry,
        }],
        geometry="geometry",
        crs=gdf.crs,
    )

    _prepare_output_path(output_path)
    result_gdf.to_file(output_path, driver="GeoJSON")

    return {
        "status": "created",
        "output_path": output_path,
        "cell_id": cell_id,
    }
