# import os
# import numpy as np
# import rasterio
 
# from rasterio.warp import calculate_default_transform, reproject, Resampling
 
 
# def calculate_heat_index_4326(geotiff_path, output_heat_path):
#     """
#     Calculate Heat Index from a single LST GeoTIFF
#     and export result as GeoTIFF in EPSG:4326.
#     """
#     if not os.path.exists(geotiff_path):
#         raise FileNotFoundError(f"File not found: {geotiff_path}")
 
#     with rasterio.open(geotiff_path) as src:
#         src_crs = src.crs
 
#         # ── Handle missing or unknown CRS ─────────
#         if src_crs is None:
#             src_crs = rasterio.crs.CRS.from_epsg(4326)
#         else:
#             try:
#                 # Try to validate the CRS — if it fails, default to 4326
#                 _ = src_crs.to_epsg()
#             except Exception:
#                 src_crs = rasterio.crs.CRS.from_epsg(4326)
 
#         lst = src.read(1).astype("float32")
#         meta = src.meta.copy()
#         src_transform = src.transform
#         src_bounds = src.bounds
 
#     # ── Clean NoData ───────────────────────────
#     nodata = meta.get("nodata")
 
#     if nodata is not None:
#         lst[lst == nodata] = np.nan
 
#     lst[lst == 0] = np.nan
 
#     valid_raw = lst[~np.isnan(lst)]
 
#     if valid_raw.size == 0:
#         raise ValueError("No valid raster pixels found.")
 
#     raw_min = np.nanmin(valid_raw)
#     raw_max = np.nanmax(valid_raw)
 
#     # ── Normalize values to Celsius ────────────
#     # Case 1: Landsat Collection 2 Thermal DN
#     if raw_max > 1000:
#         lst = lst * 0.00341802 + 149.0   # DN → Kelvin
#         lst = lst - 273.15               # Kelvin → Celsius
 
#     # Case 2: Kelvin
#     elif raw_min > 100:
#         lst = lst - 273.15               # Kelvin → Celsius
 
#     # Case 3: Already Celsius
#     else:
#         lst = lst
 
#     valid_lst = lst[~np.isnan(lst)]
 
#     if valid_lst.size == 0:
#         raise ValueError("No valid LST pixels found.")
 
#     # ── Heat Index classification ──────────────
#     heat_index = np.full(lst.shape, -9999, dtype="int16")
 
#     heat_index[lst < 27] = 0
#     heat_index[(lst >= 27) & (lst < 32)] = 1
#     heat_index[(lst >= 32) & (lst < 38)] = 2
#     heat_index[lst >= 38] = 3
 
    # heat_index[np.isnan(lst)] = -9999
    
 
#     # ── Reproject to EPSG:4326 ─────────────────
#     dst_crs = rasterio.crs.CRS.from_epsg(4326)
 
#     transform_4326, width_4326, height_4326 = calculate_default_transform(
#         src_crs,
#         dst_crs,
#         meta["width"],
#         meta["height"],
#         *src_bounds
#     )
 
#     heat_4326 = np.full(
#         (height_4326, width_4326),
#         -9999,
#         dtype="int16"
#     )
 
#     reproject(
#         source=heat_index,
#         destination=heat_4326,
#         src_transform=src_transform,
#         src_crs=src_crs,
#         dst_transform=transform_4326,
#         dst_crs=dst_crs,
#         resampling=Resampling.nearest,
#         src_nodata=-9999,
#         dst_nodata=-9999
#     )
 
#     # ── Save output ────────────────────────────
#     output_dir = os.path.dirname(output_heat_path)
#     if output_dir:
#         os.makedirs(output_dir, exist_ok=True)
 
#     meta.update({
#         "driver": "GTiff",
#         "height": height_4326,
#         "width": width_4326,
#         "transform": transform_4326,
#         "crs": dst_crs,
#         "count": 1,
#         "dtype": "int16",
#         "nodata": -9999,
#         "compress": "lzw"
#     })
 
#     with rasterio.open(output_heat_path, "w", **meta) as dst:
#         dst.write(heat_4326, 1)
 
#     # ── Stats ──────────────────────────────────
#     valid_heat = heat_4326[heat_4326 != -9999]
 
#     if valid_heat.size == 0:
#         raise ValueError("No valid heat index pixels after reprojection.")
 
#     stats = {
#         "output_path": output_heat_path,
#         "crs": str(dst_crs),
#         "valid_pixels": int(valid_heat.size),
#         "min_lst_c": round(float(np.nanmin(valid_lst)), 1),
#         "max_lst_c": round(float(np.nanmax(valid_lst)), 1),
#         "mean_lst_c": round(float(np.nanmean(valid_lst)), 1),
#         "very_cold_percent":  round(float(np.sum(valid_heat == 0) / valid_heat.size * 100), 1),
#         "cool_percent":       round(float(np.sum(valid_heat == 1) / valid_heat.size * 100), 1),
#         "ideal_percent":      round(float(np.sum(valid_heat == 2) / valid_heat.size * 100), 1),
#         "warm_percent":       round(float(np.sum(valid_heat == 3) / valid_heat.size * 100), 1),
#         "hot_percent":        round(float(np.sum(valid_heat == 4) / valid_heat.size * 100), 1),
#         "danger_percent":     round(float(np.sum(valid_heat == 5) / valid_heat.size * 100), 1),
#     }
 
#     return stats




import os
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import from_origin


# ── Band selection ────────────────────────────────────────────────────────────

def _select_thermal_band(src):
    """
    Return the 1-based band index most likely to contain LST/thermal data.

    Priority:
    1. Band description matches known thermal keywords (b10, b6, tir, lst, thermal…)
    2. Single-band file → band 1
    3. Multi-band: pick the band whose mean value most plausibly represents
       temperature (Kelvin 200–400 or Celsius -50 to 80, after ignoring
       reflectance-like bands whose values are typically 0–10000 unsigned int)
    """
    descs = [str(d or "").lower() for d in src.descriptions]
    thermal_kw = ["b10", "b6", "tir", "lst", "thermal", "temperature",
                  "st_b10", "st_b6", "band10", "band6", "lwir"]
    for i, d in enumerate(descs):
        if any(k in d for k in thermal_kw):
            return i + 1

    if src.count == 1:
        return 1

    # Sample centre of each band and pick the one whose mean falls in a
    # physically plausible temperature range (Kelvin or Celsius)
    h, w = src.height, src.width
    r0, r1 = max(0, h // 4), min(h, 3 * h // 4)
    c0, c1 = max(0, w // 4), min(w, 3 * w // 4)

    best_band, best_score = 1, -1
    for i in range(1, src.count + 1):
        chunk = src.read(i, window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)).astype("float32")
        nd = src.nodata
        valid = chunk[chunk != nd] if nd is not None else chunk
        valid = valid[valid != 0]
        valid = valid[~np.isnan(valid)]
        if valid.size == 0:
            continue
        mean = float(np.nanmean(valid))
        # Score: how close is the mean to a plausible temperature?
        # Kelvin range 250–330 K scores highest; Celsius 0–60°C scores next
        if 250 <= mean <= 340:      # Kelvin
            score = 3
        elif 0 <= mean <= 80:       # Celsius
            score = 2
        elif -60 <= mean <= 0:      # Cold Celsius (still possible)
            score = 1
        else:
            score = 0               # Probably reflectance DN, not temperature
        if score > best_score:
            best_score, best_band = score, i

    return best_band


# ── Unit detection & conversion ───────────────────────────────────────────────

def _to_celsius(raw, src_nodata):
    """
    Convert raw LST pixel values to Celsius. Handles:
      - Landsat Collection 2 Level-2 ST product (DN ~14 000–30 000)
      - Kelvin (values 200–340)
      - Celsius (values -60–80)

    Returns the Celsius array (NaN where invalid).
    """
    lst = raw.copy()

    # Mask nodata and zero
    if src_nodata is not None:
        lst[lst == src_nodata] = np.nan
    lst[lst == 0] = np.nan

    valid = lst[~np.isnan(lst)]
    if valid.size == 0:
        raise ValueError("No valid pixels found in the thermal band.")

    vmin = float(np.nanmin(valid))
    vmax = float(np.nanmax(valid))

    # Landsat Collection 2 Level-2 ST_B10 / ST_B6
    # Raw DN range ~ 7 000 – 65 535; scale = 0.00341802, offset = 149.0 → Kelvin
    if vmax > 1000:
        lst = lst * 0.00341802 + 149.0   # DN → Kelvin
        lst = lst - 273.15               # Kelvin → Celsius
        return lst

    # Already Kelvin (physically realistic: 200–340 K)
    if vmin > 150:
        lst = lst - 273.15
        return lst

    # Already Celsius (-60 to 80 is the realistic range for Earth surface)
    if -60 <= vmin and vmax <= 80:
        return lst

    raise ValueError(
        f"Cannot determine the unit of the thermal band "
        f"(raw range {vmin:.1f}–{vmax:.1f}). "
        f"Please supply a Landsat ST product (DN), a Kelvin raster, "
        f"or a Celsius LST raster."
    )


# ── Main function ─────────────────────────────────────────────────────────────

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
    # Bell-curve scoring: 20–26 °C is ideal (class 2), both colder and hotter degrade QoL.
    # class 0 : < 10 °C     very cold
    # class 1 : 10–20 °C    cool
    # class 2 : 20–26 °C    ideal (peak score)
    # class 3 : 26–32 °C    warm
    # class 4 : 32–38 °C    hot
    # class 5 : ≥ 38 °C     danger
    heat_index = np.full(lst.shape, -9999, dtype="int16")

    heat_index[lst < 10]                       = 0
    heat_index[(lst >= 10) & (lst < 20)]       = 1
    heat_index[(lst >= 20) & (lst < 26)]       = 2
    heat_index[(lst >= 26) & (lst < 32)]       = 3
    heat_index[(lst >= 32) & (lst < 38)]       = 4
    heat_index[lst >= 38]                      = 5

    heat_index[np.isnan(lst)] = -9999
    heat_4326 = heat_index
    transform_4326 = src_transform
    width_4326 = meta["width"]
    height_4326 = meta["height"]
    dst_crs = meta["crs"]

    # ── Reproject to EPSG:4326 ─────────────────
    # dst_crs = "EPSG:4326"

    # transform_4326, width_4326, height_4326 = calculate_default_transform(
    #     src_crs,
    #     dst_crs,
    #     meta["width"],
    #     meta["height"],
    #     *src_bounds
    # )

    # heat_4326 = np.full(
    #     (height_4326, width_4326),
    #     -9999,
    #     dtype="int16"
    # )

    # reproject(
    #     source=heat_index,
    #     destination=heat_4326,
    #     src_transform=src_transform,
    #     src_crs=src_crs,
    #     dst_transform=transform_4326,
    #     dst_crs=dst_crs,
    #     resampling=Resampling.nearest,
    #     src_nodata=-9999,
    #     dst_nodata=-9999
    # )

    # ── Save output ────────────────────────────
    output_dir = os.path.dirname(output_heat_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    meta.update({
        "driver":    "GTiff",
        "height":    height_4326,
        "width":     width_4326,
        "transform": transform_4326,
        "crs":       dst_crs,
        "count":     1,
        "dtype":     "int16",
        "nodata":    -9999,
        "compress":  "lzw",
    })

    with rasterio.open(output_heat_path, "w", **meta) as dst:
        dst.write(heat_4326, 1)

    # ── Stats ──────────────────────────────────
    valid_heat = heat_4326[heat_4326 != -9999]
    if valid_heat.size == 0:
        raise ValueError("No valid heat index pixels after processing.")

    stats = {
        "output_path": output_heat_path,
        "crs": dst_crs,
        "valid_pixels": int(valid_heat.size),
        "min_lst_c": round(float(np.nanmin(valid_lst)), 1),
        "max_lst_c": round(float(np.nanmax(valid_lst)), 1),
        "mean_lst_c": round(float(np.nanmean(valid_lst)), 1),
        "very_cold_percent":  round(float(np.sum(valid_heat == 0) / valid_heat.size * 100), 1),
        "cool_percent":       round(float(np.sum(valid_heat == 1) / valid_heat.size * 100), 1),
        "ideal_percent":      round(float(np.sum(valid_heat == 2) / valid_heat.size * 100), 1),
        "warm_percent":       round(float(np.sum(valid_heat == 3) / valid_heat.size * 100), 1),
        "hot_percent":        round(float(np.sum(valid_heat == 4) / valid_heat.size * 100), 1),
        "danger_percent":     round(float(np.sum(valid_heat == 5) / valid_heat.size * 100), 1),
    }

    print("MIN:", np.nanmin(valid_lst))
    print("MAX:", np.nanmax(valid_lst))
    print("UNIQUE HEAT:", np.unique(heat_4326))

    return stats