import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask

# Band indices are 1-based (rasterio convention)
_BAND_MAP = {
    # Landsat 8/9: 11-band OLI/TIRS stack; Red=B4, NIR=B5
    "landsat": (4, 5),
    # Sentinel-2: 13-band MSI stack (B1…B8A,B9,B10,B11,B12); Red=B4(idx4), NIR=B8(idx8)
    "sentinel2": (4, 8),
}


def _detect_bands(src):
    """
    Infer Red and NIR band indices from the rasterio dataset.

    Detection order:
    1. Dataset-level metadata tags (SPACECRAFT_ID / SATELLITE).
    2. Band count heuristic:
       - 2 bands  → pre-extracted Red+NIR (bands 1, 2)
       - 11 bands → Landsat 8/9 OLI/TIRS full stack
       - 13 bands → Sentinel-2 MSI full stack
       - 7 bands  → Landsat 4-7 TM/ETM+ (Red=B3, NIR=B4)
    3. Fall back to Landsat 8/9 mapping for any other band count.

    Returns (red_band_index, nir_band_index) — both 1-based.
    """
    tags = {k.lower(): v.lower() for k, v in (src.tags() or {}).items()}

    spacecraft = tags.get("spacecraft_id", "") or tags.get("satellite", "")
    if "sentinel" in spacecraft:
        return _BAND_MAP["sentinel2"]
    if "landsat" in spacecraft:
        # Landsat 4-7 TM/ETM+ stacks are 7 bands: Red=3, NIR=4
        if src.count == 7:
            return (3, 4)
        return _BAND_MAP["landsat"]

    # Heuristic fallback on band count
    n = src.count
    if n == 2:
        return (1, 2)
    if n == 4:
        # 4-band subsets (Blue/Green/Red/NIR): Red=3, NIR=4
        return (3, 4)
    if n == 13:
        return _BAND_MAP["sentinel2"]
    if n == 7:
        return (3, 4)   # Landsat 4-7
    # 11 bands or anything else → Landsat 8/9 mapping
    return _BAND_MAP["landsat"]


def calculate_ndvi_from_bands(geotiff_path, output_ndvi_path):
    """
    Extract Red and NIR bands from a single multi-band GeoTIFF and compute NDVI.

    The satellite type and correct band indices are detected automatically from
    the file's metadata tags and band count.

    Parameters
    ----------
    geotiff_path     : path to the multi-band GeoTIFF (Landsat 8/9, Sentinel-2, or pre-extracted 2-band)
    output_ndvi_path : where to write the output NDVI GeoTIFF
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    with rasterio.open(geotiff_path) as src:
        red_band_index, nir_band_index = _detect_bands(src)

        band_count = src.count
        if red_band_index > band_count or nir_band_index > band_count:
            raise ValueError(
                f"File has {band_count} band(s) but detected band indices "
                f"{red_band_index} (Red) and {nir_band_index} (NIR) are out of range."
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

