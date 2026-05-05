import os
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling


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
    Calculate Heat Index from an LST GeoTIFF and export as EPSG:4326 GeoTIFF.

    Accepts:
      - Landsat Collection 2 Level-2 ST product (Band 10 / Band 6, raw DN)
      - Single-band Kelvin raster
      - Single-band Celsius raster
      - Multi-band raster — thermal band is auto-detected

    Returns a dict with temperature stats and class percentages.
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"File not found: {geotiff_path}")

    with rasterio.open(geotiff_path) as src:
        src_crs = src.crs
        if src_crs is None:
            raise ValueError("GeoTIFF has no CRS. Please supply a georeferenced raster.")

        band_idx     = _select_thermal_band(src)
        raw          = src.read(band_idx).astype("float32")
        meta         = src.meta.copy()
        src_transform = src.transform
        src_bounds   = src.bounds
        src_nodata   = src.nodata

    # ── Convert to Celsius ────────────────────────────────────────────────────
    lst = _to_celsius(raw, src_nodata)

    valid_lst = lst[~np.isnan(lst)]
    if valid_lst.size == 0:
        raise ValueError("No valid LST pixels found after conversion.")

    lst_min  = float(np.nanmin(valid_lst))
    lst_max  = float(np.nanmax(valid_lst))
    lst_mean = float(np.nanmean(valid_lst))

    # Sanity check — Cairo in summer peaks ~50°C; anything below -60°C is suspect
    if lst_max < -50 or lst_min > 100:
        raise ValueError(
            f"Temperature values out of expected range after conversion "
            f"({lst_min:.1f}°C – {lst_max:.1f}°C). "
            f"The uploaded file may not be an LST raster."
        )

    # ── Classify into heat-index tiers ────────────────────────────────────────
    heat_index = np.full(lst.shape, -9999, dtype="int16")
    heat_index[~np.isnan(lst) & (lst < 27)]                    = 0  # comfortable
    heat_index[~np.isnan(lst) & (lst >= 27) & (lst < 32)]      = 1  # caution
    heat_index[~np.isnan(lst) & (lst >= 32) & (lst < 38)]      = 2  # extreme caution
    heat_index[~np.isnan(lst) & (lst >= 38)]                   = 3  # danger
    heat_index[np.isnan(lst)]                                   = -9999

    # ── Reproject to EPSG:4326 ────────────────────────────────────────────────
    dst_crs = "EPSG:4326"

    transform_4326, width_4326, height_4326 = calculate_default_transform(
        src_crs, dst_crs, meta["width"], meta["height"], *src_bounds
    )

    heat_4326 = np.full((height_4326, width_4326), -9999, dtype="int16")

    reproject(
        source=heat_index,
        destination=heat_4326,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=transform_4326,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
        src_nodata=-9999,
        dst_nodata=-9999,
    )

    # ── Save output ───────────────────────────────────────────────────────────
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

    # ── Stats ─────────────────────────────────────────────────────────────────
    valid_heat = heat_4326[heat_4326 != -9999]
    if valid_heat.size == 0:
        raise ValueError("No valid heat index pixels after reprojection.")

    n = valid_heat.size
    return {
        "output_path":            output_heat_path,
        "crs":                    dst_crs,
        "valid_pixels":           int(n),
        "band_used":              band_idx,
        "min_lst_c":              round(lst_min,  1),
        "max_lst_c":              round(lst_max,  1),
        "mean_lst_c":             round(lst_mean, 1),
        "comfortable_percent":    round(float(np.sum(valid_heat == 0) / n * 100), 1),
        "caution_percent":        round(float(np.sum(valid_heat == 1) / n * 100), 1),
        "extreme_caution_percent":round(float(np.sum(valid_heat == 2) / n * 100), 1),
        "danger_percent":         round(float(np.sum(valid_heat == 3) / n * 100), 1),
    }
