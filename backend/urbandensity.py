"""
urbandensity.py
Calculates urban density (population per unit area) for a given region.
"""

import geopandas as gpd
import pandas as pd


def calculate_urban_density(population_geojson, population_field, output_path=None):
    """
    Calculates urban density (population per unit area) for each polygon in a GeoJSON file.
    Automatically calculates the area of each polygon in square kilometers.

    Parameters
    ----------
    population_geojson : str
        Path to the input GeoJSON file containing population data and polygon geometries.
    population_field : str
        Name of the field containing population values.
    output_path : str, optional
        Path to save the output GeoJSON with density values. If None, does not save.

    Returns
    -------
    GeoDataFrame with new 'area_km2' and 'urban_density' columns.
    """
    gdf = gpd.read_file(population_geojson)

    if population_field not in gdf.columns:
        raise ValueError(f"Specified population field '{population_field}' not found in GeoJSON.")

    # Ensure we have a projected CRS for accurate area calculations
    if gdf.crs is None:
        # Assume WGS84 if no CRS is specified
        gdf = gdf.set_crs('EPSG:4326')

    # Convert to a projected CRS for area calculations (using UTM zone based on centroid)
    if gdf.crs != 'EPSG:4326':
        # If already projected, use as is
        gdf_projected = gdf.copy()
    else:
        # Convert from geographic to projected coordinates
        # Use UTM zone based on the centroid of the data
        centroid = gdf.geometry.centroid
        lon = centroid.x.mean()
        lat = centroid.y.mean()

        # Determine UTM zone
        utm_zone = int((lon + 180) / 6) + 1
        if lat >= 0:
            epsg_code = 32600 + utm_zone  # Northern hemisphere
        else:
            epsg_code = 32700 + utm_zone  # Southern hemisphere

        try:
            gdf_projected = gdf.to_crs(f'EPSG:{epsg_code}')
        except:
            # Fallback to Web Mercator if UTM fails
            gdf_projected = gdf.to_crs('EPSG:3857')

    # Calculate area in square kilometers
    gdf['area_km2'] = gdf_projected.geometry.area / 1000000  # Convert m² to km²

    # Calculate urban density (population per km²)
    gdf['urban_density'] = gdf[population_field] / gdf['area_km2']

    if output_path:
        gdf.to_file(output_path)
    return gdf

# Example usage (uncomment and edit paths/fields to use):
# result = calculate_urban_density('city_blocks.geojson', 'population', 'urban_density_output.geojson')
# print(result[['area_km2', 'urban_density']])
