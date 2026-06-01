"""
building_density.py
Calculates building density from a raster: building area / total land area.
Scored against the urban planning standard of 10–25 dwelling units per acre
(optimal range gets 100; values outside degrade symmetrically).

Units-per-acre conversion
--------------------------
The raster contains pixel values representing building area fraction (0–1)
OR raw building coverage where each pixel counts as 1 unit.
We compute density as:

    building_density_pct  = (building_pixels / total_valid_pixels) × 100
    units_per_acre         ≈ building_density_pct × PIXEL_DENSITY_SCALE

Since we cannot know the absolute number of dwelling units from a plain
building-mask raster, we map building coverage percentage onto a
units-per-acre scale using a calibration constant (1 % coverage ≈ 0.8 u/acre
based on typical urban form assumptions).  This keeps scoring meaningful
and consistent regardless of the specific raster source.

Returns per-cell GeoJSON + overall stats dict.
"""

import os
import json
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import xy
from shapely.geometry import box, mapping


# ── Constants ─────────────────────────────────────────────────────────────────

OPTIMAL_LOW   = 10.0   # lower bound of ideal range (units/acre)
OPTIMAL_HIGH  = 25.0   # upper bound of ideal range (units/acre)
PCT_TO_UPA    = 0.8    # 1% building coverage ≈ 0.8 units/acre (calibration)

# Pixel values considered "built" in single-band rasters
# Values > BUILDING_THRESHOLD are treated as building pixels.
BUILDING_THRESHOLD = 0.5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_wgs84(src_path: str, dst_path: str) -> str:
    """Reproject raster to EPSG:4326 if needed (rasterio-only, no pyproj)."""
    with rasterio.open(src_path) as src:
        if src.crs is None:
            return src_path
        try:
            crs_str = src.crs.to_string().upper()
            if "EPSG:4326" in crs_str or "WGS84" in crs_str or "WGS 84" in crs_str:
                return src_path
        except Exception:
            pass

        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds
        )
        meta = src.meta.copy()
        meta.update({
            "crs": "EPSG:4326",
            "transform": transform,
            "width": width,
            "height": height,
            "driver": "GTiff",
        })
        with rasterio.open(dst_path, "w", **meta) as dst:
            for band in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, band),
                    destination=rasterio.band(dst, band),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs="EPSG:4326",
                    resampling=Resampling.nearest,
                )
    return dst_path


def _adaptive_cell_size_px(width: int, height: int, target_cells: int = 200) -> int:
    raw = (width * height / target_cells) ** 0.5
    return max(5, int(round(raw)))


def score_building_density(units_per_acre: float) -> int:
    """
    Map units-per-acre value to a QoL score 0–100.

    Optimal range: 10–25 u/acre → 100
    Graceful degradation outside that range:

    Below 10 (under-built / too sparse):
      10  → 100
       5  →  60
       2  →  30
       0  →   0

    Above 25 (over-built / too dense):
      25  → 100
      40  →  70
      60  →  40
      80  →  15
     100+ →   0
    """
    if units_per_acre is None or np.isnan(units_per_acre) or units_per_acre < 0:
        return 0

    u = float(units_per_acre)

    if OPTIMAL_LOW <= u <= OPTIMAL_HIGH:
        return 100

    if u < OPTIMAL_LOW:
        # Too sparse
        if u >= 5:
            return int(np.interp(u, [5, OPTIMAL_LOW], [60, 100]))
        if u >= 2:
            return int(np.interp(u, [2, 5], [30, 60]))
        return int(np.interp(u, [0, 2], [0, 30]))

    # Too dense (u > OPTIMAL_HIGH)
    if u <= 40:
        return int(np.interp(u, [OPTIMAL_HIGH, 40], [100, 70]))
    if u <= 60:
        return int(np.interp(u, [40, 60], [70, 40]))
    if u <= 80:
        return int(np.interp(u, [60, 80], [40, 15]))
    return int(np.interp(min(u, 120), [80, 120], [15, 0]))


# ── Main analysis function ────────────────────────────────────────────────────

def calculate_building_density(
    geotiff_path: str,
    building_threshold: float = BUILDING_THRESHOLD,
    output_path: str = None,
    tmp_dir: str = None,
) -> dict:
    """
    Analyse building density from a GeoTIFF raster.

    Accepts:
    - A single-band building mask raster (pixel values > threshold = built).
    - A multi-band raster: band 1 is used as the mask.

    Returns
    -------
    dict with keys:
        building_pct        – % of valid pixels that are built (float)
        units_per_acre      – estimated dwelling units per acre (float)
        overall_score       – QoL score 0–100 (int)
        valid_pixels        – count of valid (non-nodata) pixels
        building_pixels     – count of built pixels
        cell_size_m         – approximate cell size used for the grid
        cell_geojson        – per-cell GeoJSON FeatureCollection (dict)
        optimal_low         – lower bound of ideal range (10)
        optimal_high        – upper bound of ideal range (25)
        in_optimal_range    – bool
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    scratch = tmp_dir or os.path.dirname(geotiff_path) or "."
    wgs_path = os.path.join(scratch, "_bd_wgs84.tif")
    work_path = _ensure_wgs84(geotiff_path, wgs_path)

    with rasterio.open(work_path) as src:
        transform     = src.transform
        raster_bounds = src.bounds
        raster_width  = src.width
        raster_height = src.height
        nodata        = src.nodata if src.nodata is not None else -9999

        band = src.read(1).astype("float32")

    # Mask nodata
    band[band == nodata] = np.nan

    valid_mask   = ~np.isnan(band)
    valid_pixels = int(valid_mask.sum())
    if valid_pixels == 0:
        raise ValueError("No valid pixels found in the raster. Check the file.")

    # Classify as building / non-building
    build_mask   = valid_mask & (band > building_threshold)
    build_pixels = int(build_mask.sum())

    building_pct   = build_pixels / valid_pixels * 100.0
    units_per_acre = building_pct * PCT_TO_UPA
    overall_score  = score_building_density(units_per_acre)
    in_optimal     = OPTIMAL_LOW <= units_per_acre <= OPTIMAL_HIGH

    # ── Per-cell grid ─────────────────────────────────────────────────────────
    cell_px = _adaptive_cell_size_px(raster_width, raster_height)

    lat_span_deg = abs(raster_bounds.top - raster_bounds.bottom)
    cell_m = max(100, int(round(lat_span_deg / raster_height * cell_px * 111_000)))

    features = []
    for row_start in range(0, raster_height, cell_px):
        row_end = min(row_start + cell_px, raster_height)
        for col_start in range(0, raster_width, cell_px):
            col_end = min(col_start + cell_px, raster_width)

            cell_data  = band[row_start:row_end, col_start:col_end]
            cell_valid = cell_data[~np.isnan(cell_data)]
            if len(cell_valid) == 0:
                continue

            cell_build_n   = int((cell_valid > building_threshold).sum())
            cell_build_pct = cell_build_n / len(cell_valid) * 100.0
            cell_upa       = cell_build_pct * PCT_TO_UPA
            cell_score     = score_building_density(cell_upa)

            # Pixel corners → lon/lat via rasterio
            left,  bottom = xy(transform, row_end,   col_start, offset="ul")
            right, top    = xy(transform, row_start, col_end,   offset="ul")
            cell_lon_min = min(left, right)
            cell_lon_max = max(left, right)
            cell_lat_min = min(bottom, top)
            cell_lat_max = max(bottom, top)
            cell_cx = (cell_lon_min + cell_lon_max) / 2
            cell_cy = (cell_lat_min + cell_lat_max) / 2

            features.append({
                "type": "Feature",
                "geometry": mapping(box(cell_lon_min, cell_lat_min,
                                        cell_lon_max, cell_lat_max)),
                "properties": {
                    "building_pct":    round(cell_build_pct, 2),
                    "units_per_acre":  round(cell_upa, 2),
                    "qol_score":       cell_score,
                    "in_optimal":      OPTIMAL_LOW <= cell_upa <= OPTIMAL_HIGH,
                    "cell_cx":         round(cell_cx, 6),
                    "cell_cy":         round(cell_cy, 6),
                    "service":         "building-density",
                },
            })

    cell_geojson = {
        "type":             "FeatureCollection",
        "features":         features,
        "cell_size_m":      cell_m,
        "building_pct":     round(building_pct, 2),
        "units_per_acre":   round(units_per_acre, 2),
        "optimal_low":      OPTIMAL_LOW,
        "optimal_high":     OPTIMAL_HIGH,
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(cell_geojson, fh)

    return {
        "building_pct":    round(building_pct, 2),
        "units_per_acre":  round(units_per_acre, 2),
        "overall_score":   overall_score,
        "valid_pixels":    valid_pixels,
        "building_pixels": build_pixels,
        "cell_size_m":     cell_m,
        "cell_geojson":    cell_geojson,
        "optimal_low":     OPTIMAL_LOW,
        "optimal_high":    OPTIMAL_HIGH,
        "in_optimal_range": in_optimal,
    }
