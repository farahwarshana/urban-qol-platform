import os
import numpy as np
import rasterio

from rasterio.warp import calculate_default_transform, reproject, Resampling


def calculate_heat_index_4326(geotiff_path, output_heat_path):
    """
    Calculate Heat Index from a single LST GeoTIFF
    and export result as GeoTIFF in EPSG:4326.
    """

    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"File not found: {geotiff_path}")

    with rasterio.open(geotiff_path) as src:
        src_crs = src.crs

        if src_crs is None:
            raise ValueError("LST GeoTIFF has no CRS.")

        lst = src.read(1).astype("float32")
        meta = src.meta.copy()
        src_transform = src.transform
        src_bounds = src.bounds

    # ── Clean NoData ───────────────────────────
    nodata = meta.get("nodata")

    if nodata is not None:
        lst[lst == nodata] = np.nan

    lst[lst == 0] = np.nan

    valid_raw = lst[~np.isnan(lst)]

    if valid_raw.size == 0:
        raise ValueError("No valid raster pixels found.")

    raw_min = np.nanmin(valid_raw)
    raw_max = np.nanmax(valid_raw)

    # ── Normalize values to Celsius ────────────
    # Case 1: Landsat Collection 2 Thermal DN
    if raw_max > 1000:
        lst = lst * 0.00341802 + 149.0   # DN → Kelvin
        lst = lst - 273.15               # Kelvin → Celsius

    # Case 2: Kelvin
    elif raw_min > 100:
        lst = lst - 273.15               # Kelvin → Celsius

    # Case 3: Already Celsius
    else:
        lst = lst

    valid_lst = lst[~np.isnan(lst)]

    if valid_lst.size == 0:
        raise ValueError("No valid LST pixels found.")

    # ── Heat Index classification ──────────────
    heat_index = np.full(lst.shape, -9999, dtype="int16")

    heat_index[lst < 27] = 0
    heat_index[(lst >= 27) & (lst < 32)] = 1
    heat_index[(lst >= 32) & (lst < 38)] = 2
    heat_index[lst >= 38] = 3

    heat_index[np.isnan(lst)] = -9999

    # ── Reproject to EPSG:4326 ─────────────────
    dst_crs = "EPSG:4326"

    transform_4326, width_4326, height_4326 = calculate_default_transform(
        src_crs,
        dst_crs,
        meta["width"],
        meta["height"],
        *src_bounds
    )

    heat_4326 = np.full(
        (height_4326, width_4326),
        -9999,
        dtype="int16"
    )

    reproject(
        source=heat_index,
        destination=heat_4326,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=transform_4326,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
        src_nodata=-9999,
        dst_nodata=-9999
    )

    # ── Save output ────────────────────────────
    output_dir = os.path.dirname(output_heat_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    meta.update({
        "driver": "GTiff",
        "height": height_4326,
        "width": width_4326,
        "transform": transform_4326,
        "crs": dst_crs,
        "count": 1,
        "dtype": "int16",
        "nodata": -9999,
        "compress": "lzw"
    })

    with rasterio.open(output_heat_path, "w", **meta) as dst:
        dst.write(heat_4326, 1)

    # ── Stats ──────────────────────────────────
    valid_heat = heat_4326[heat_4326 != -9999]

    if valid_heat.size == 0:
        raise ValueError("No valid heat index pixels after reprojection.")

    stats = {
        "output_path": output_heat_path,
        "crs": dst_crs,
        "valid_pixels": int(valid_heat.size),
        "min_lst_c": round(float(np.nanmin(valid_lst)), 1),
        "max_lst_c": round(float(np.nanmax(valid_lst)), 1),
        "mean_lst_c": round(float(np.nanmean(valid_lst)), 1),
        "comfortable_percent": round(float(np.sum(valid_heat == 0) / valid_heat.size * 100), 1),
        "caution_percent": round(float(np.sum(valid_heat == 1) / valid_heat.size * 100), 1),
        "extreme_caution_percent": round(float(np.sum(valid_heat == 2) / valid_heat.size * 100), 1),
        "danger_percent": round(float(np.sum(valid_heat == 3) / valid_heat.size * 100), 1),
    }

    print("MIN:", np.nanmin(valid_lst))
    print("MAX:", np.nanmax(valid_lst))
    print("UNIQUE HEAT:", np.unique(heat_4326))

    return stats