import os
import geopandas as gpd

INPUT_FOLDER = "ai_agent/outputs"
OUTPUT_FILE = "ai_agent/outputs/ai_recommendation_layers.geojson"


def merge_geojson_files():
    files = [
        f for f in os.listdir(INPUT_FOLDER)
        if f.endswith(".geojson")
        and "cell_" in f  # only recommendation files
    ]

    if not files:
        print("No GeoJSON files found to merge.")
        return

    gdfs = []

    for file in files:
        path = os.path.join(INPUT_FOLDER, file)
        gdf = gpd.read_file(path)
        gdfs.append(gdf)

    merged = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True),
        crs=gdfs[0].crs
    )

    merged.to_file(OUTPUT_FILE, driver="GeoJSON")

    print(f"Merged {len(files)} files into:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    import pandas as pd
    merge_geojson_files()