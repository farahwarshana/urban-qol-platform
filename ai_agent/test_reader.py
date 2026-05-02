import os
import sys
import geopandas as gpd


def main():
    """
    Read and analyze grid features GeoJSON file.
    Checks for file existence, reads GIS output, and prints statistics.
    """
    
    # Define the file path
    file_path = "outputs/features/grid_features.geojson"
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        print("Please make sure the GIS processing pipeline has generated the grid features file.")
        sys.exit(1)
    
    print("=" * 70)
    print("GRID FEATURES DATA READER")
    print("=" * 70)
    print()
    
    # Read the GeoJSON file
    try:
        gdf = gpd.read_file(file_path)
        print(f"✓ Successfully loaded: {file_path}")
        print()
        
        # Print column names
        print("COLUMN NAMES:")
        print("-" * 70)
        for i, col in enumerate(gdf.columns, 1):
            print(f"  {i}. {col}")
        print()
        
        # Print first 5 rows
        print("FIRST 5 ROWS:")
        print("-" * 70)
        print(gdf.head())
        print()
        
        # Print total number of grid cells
        total_cells = len(gdf)
        print("DATA SUMMARY:")
        print("-" * 70)
        print(f"  Total number of grid cells: {total_cells}")
        print()
        
        # List of columns to calculate averages for
        target_columns = [
            'ndvi_mean',
            'lst_mean',
            'built_up_density',
            'road_density',
            'dist_station_m',
            'priority_score'
        ]
        
        # Calculate and print averages
        print("COLUMN AVERAGES:")
        print("-" * 70)
        for col in target_columns:
            if col in gdf.columns:
                try:
                    avg_value = gdf[col].mean()
                    print(f"  {col}: {avg_value:.6f}")
                except Exception as e:
                    print(f"  {col}: Error calculating mean - {str(e)}")
            else:
                print(f"  Column not found: {col}")
        
        print()
        print("=" * 70)
        print("SUCCESS: Data reading completed")
        print("=" * 70)
        
    except Exception as e:
        print(f"ERROR: Failed to read file: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
