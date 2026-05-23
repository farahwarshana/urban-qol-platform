# from curses import meta
import os
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling


def detect_pollutant(filename):
    name = os.path.basename(filename).lower()
    if "pm25" in name or "pm2.5" in name:
        return "PM25"
    if "pm10" in name:
        return "PM10"
    if "no2" in name:
        return "NO2"
    if "aqi" in name:
        return "AQI"
    return "AQI"  # default: treat single-band raster as pre-computed AQI


def classify_aqi(data, pollutant):
    aqi = np.full(data.shape, -9999, dtype="int16")

    if pollutant == "PM25":
        aqi[data <= 12]  = 0
        aqi[(data > 12)  & (data <= 35.4)] = 1
        aqi[(data > 35.4) & (data <= 55.4)] = 2
        aqi[(data > 55.4) & (data <= 150)]  = 3
        aqi[(data > 150) & (data <= 250)]   = 4
        aqi[data > 250]  = 5
    elif pollutant == "PM10":
        aqi[data <= 54]  = 0
        aqi[(data > 54)  & (data <= 154)] = 1
        aqi[(data > 154) & (data <= 254)] = 2
        aqi[(data > 254) & (data <= 354)] = 3
        aqi[(data > 354) & (data <= 424)] = 4
        aqi[data > 424]  = 5
    elif pollutant == "NO2":
        aqi[data <= 0.00005] = 0
        aqi[(data > 0.00005) & (data <= 0.00010)] = 1
        aqi[(data > 0.00010) & (data <= 0.00015)] = 2
        aqi[(data > 0.00015) & (data <= 0.00020)] = 3
        aqi[(data > 0.00020) & (data <= 0.00030)] = 4
        aqi[data > 0.00030] = 5
    else:  # AQI direct
        aqi[data <= 50]  = 0
        aqi[(data > 50)  & (data <= 100)] = 1
        aqi[(data > 100) & (data <= 150)] = 2
        aqi[(data > 150) & (data <= 200)] = 3
        aqi[(data > 200) & (data <= 300)] = 4
        aqi[data > 300]  = 5

    aqi[np.isnan(data)] = -9999
    return aqi


def calculate_air_quality_index(geotiff_path, output_path):
    """
    Classify a pollutant or AQI raster into 6 AQI categories (0–5) and
    reproject to EPSG:4326.

    Parameters
    ----------
    geotiff_path : str  – path to input GeoTIFF (PM2.5 / PM10 / NO2 / AQI)
    output_path  : str  – path where the classified output GeoTIFF is written

    Returns
    -------
    dict with processing stats
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"File not found: {geotiff_path}")

    pollutant = detect_pollutant(geotiff_path)

    with rasterio.open(geotiff_path) as src:
        src_crs   = src.crs
        data      = src.read(1).astype("float32")
        transform = src.transform
        meta      = src.meta.copy()

    if src_crs is None:
        raise ValueError("Input GeoTIFF has no CRS.")

    nodata = meta.get("nodata")
    if nodata is not None:
        data[data == nodata] = np.nan
    data[data == 0] = np.nan

    if np.all(np.isnan(data)):
        raise ValueError("No valid raster pixels found.")

    aqi = classify_aqi(data, pollutant)

    # dst_crs = "EPSG:4326"
    # transform_4326, w, h = calculate_default_transform(
    #     src_crs, dst_crs, meta["width"], meta["height"],
    #     *rasterio.transform.array_bounds(meta["height"], meta["width"], transform),
    # )

    dst_crs = src_crs
    transform_4326 = transform
    w = meta["width"]
    h = meta["height"]
    out = aqi  

    out = np.full((h, w), -9999, dtype="int16")
    reproject(
        source=aqi,
        destination=out,
        src_transform=transform,
        src_crs=src_crs,
        dst_transform=transform_4326,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
        src_nodata=-9999,
        dst_nodata=-9999,
    )

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    meta.update({
        "driver":    "GTiff",
        "height":    h,
        "width":     w,
        "transform": transform_4326,
        "crs":       dst_crs,
        "count":     1,
        "dtype":     "int16",
        "nodata":    -9999,
        "compress":  "lzw",
    })
    with rasterio.open(output_path, "w", **meta) as dst:
        dst.write(out, 1)

    valid = out[out != -9999]
    if valid.size == 0:
        raise ValueError("No valid AQI pixels after reprojection.")

    total = valid.size

    stats = {
    "output_path":      output_path,
    "crs":              dst_crs,
    "pollutant":        pollutant,
    "valid_pixels":     int(total),
    "good_pct":         round(float(np.sum(valid == 0) / total * 100), 1),
    "moderate_pct":     round(float(np.sum(valid == 1) / total * 100), 1),
    "sensitive_pct":    round(float(np.sum(valid == 2) / total * 100), 1),
    "unhealthy_pct":    round(float(np.sum(valid == 3) / total * 100), 1),
    "very_unhealthy_pct": round(float(np.sum(valid == 4) / total * 100), 1),
    "hazardous_pct":    round(float(np.sum(valid == 5) / total * 100), 1),
}

    stats["score"] = round(
    (
        stats["good_pct"] * 100 +
        stats["moderate_pct"] * 75 +
        stats["sensitive_pct"] * 55 +
        stats["unhealthy_pct"] * 35 +
        stats["very_unhealthy_pct"] * 15 +
        stats["hazardous_pct"] * 0
    ) / 100
)

    return stats