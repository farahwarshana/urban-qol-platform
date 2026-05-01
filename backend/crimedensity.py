"""
crimedensity.py
Maps and analyzes the concentration of crime incidents across an area.
"""

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def calculate_crime_density(crime_csv, area_shapefile, lat_field, lon_field, output_path=None):
    """
    Maps and analyzes the concentration of crime incidents (crime density) per area unit.

    Parameters
    ----------
    crime_csv : str
        Path to CSV file with crime incident locations (latitude, longitude).
    area_shapefile : str
        Path to shapefile/GeoJSON of polygons (e.g., neighborhoods, districts).
    lat_field : str
        Name of latitude field in CSV.
    lon_field : str
        Name of longitude field in CSV.
    output_path : str, optional
        Path to save the output shapefile/GeoJSON with crime density values. If None, does not save.

    Returns
    -------
    GeoDataFrame with a new 'crime_density' column (incidents per area unit).
    """
    # Load area polygons
    areas = gpd.read_file(area_shapefile)
    
    # Load crime points
    crimes = pd.read_csv(crime_csv)
    
    # Find matching column names (case-insensitive)
    lat_col = None
    lon_col = None
    for col in crimes.columns:
        if col.lower() == lat_field.lower():
            lat_col = col
        if col.lower() == lon_field.lower():
            lon_col = col
    
    if lat_col is None:
        raise ValueError(f"Latitude column '{lat_field}' not found in CSV. Available columns: {list(crimes.columns)}")
    if lon_col is None:
        raise ValueError(f"Longitude column '{lon_field}' not found in CSV. Available columns: {list(crimes.columns)}")
    
    # Create geometry from points
    geometry = [Point(xy) for xy in zip(crimes[lon_col], crimes[lat_col])]
    
    # Determine CRS for the crimes - default to WGS84 if areas don't have one
    crs = areas.crs if areas.crs is not None else "EPSG:4326"
    crimes_gdf = gpd.GeoDataFrame(crimes, geometry=geometry, crs=crs)

    # Spatial join: assign each crime to a polygon
    joined = gpd.sjoin(crimes_gdf, areas, how="inner", predicate="within")
    # Count crimes per polygon
    crime_counts = joined.groupby(joined.index_right).size()
    areas['crime_count'] = areas.index.map(crime_counts).fillna(0).astype(int)
    # Calculate area in km^2 if not present
    if 'area_km2' not in areas.columns:
        areas = areas.to_crs(epsg=3857)
        areas['area_km2'] = areas.geometry.area / 1e6
    areas['crime_density'] = areas['crime_count'] / areas['area_km2']

    # Convert back to WGS84 (EPSG:4326) for proper display in Leaflet
    areas_wgs84 = areas.to_crs(epsg=4326)

    if output_path:
        areas_wgs84.to_file(output_path)
    return areas_wgs84

# Example usage (uncomment and edit paths/fields to use):
# result = calculate_crime_density('crimes.csv', 'neighborhoods.shp', 'latitude', 'longitude', 'crime_density_output.shp')
# print(result[['crime_density']])
