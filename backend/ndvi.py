import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask


def calculate_ndvi_from_bands(geotiff_path, red_band_index, nir_band_index, output_ndvi_path):
    """
    Extract Red and NIR bands from a single multi-band GeoTIFF and compute NDVI.

    Parameters
    ----------
    geotiff_path     : path to the multi-band Landsat GeoTIFF
    red_band_index   : band number for Red (Landsat 8/9 = 4)
    nir_band_index   : band number for NIR (Landsat 8/9 = 5)
    output_ndvi_path : where to write the output NDVI GeoTIFF
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    with rasterio.open(geotiff_path) as src:
        band_count = src.count
        if red_band_index > band_count or nir_band_index > band_count:
            raise ValueError(
                f"File has {band_count} band(s) but band indices "
                f"{red_band_index} (Red) and {nir_band_index} (NIR) were requested."
            )

        red = src.read(red_band_index).astype("float32")
        nir = src.read(nir_band_index).astype("float32")
        meta = src.meta.copy()

    # Treat zero pixels as NoData
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan

    denominator = nir + red

    ndvi = np.where(
        np.isnan(denominator) | (denominator == 0),
        np.nan,
        (nir - red) / denominator,
    ).astype("float32")

    meta.update({
        "driver": "GTiff",
        "count":  1,
        "dtype":  "float32",
        "nodata": -9999,
    })

    ndvi_output = np.where(np.isnan(ndvi), -9999, ndvi).astype("float32")

    output_dir = os.path.dirname(output_ndvi_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with rasterio.open(output_ndvi_path, "w", **meta) as dst:
        dst.write(ndvi_output, 1)

    valid_ndvi = ndvi[~np.isnan(ndvi)]
    stats = {"output_path": output_ndvi_path, "valid_pixels": int(valid_ndvi.size)}

    if valid_ndvi.size > 0:
        stats.update({
            "min":  float(np.nanmin(valid_ndvi)),
            "max":  float(np.nanmax(valid_ndvi)),
            "mean": float(np.nanmean(valid_ndvi)),
        })
    else:
        stats["warning"] = "No valid NDVI pixels found."

    return stats

