"""
vegetation_density.py
Vegetation density analysis for urban planners.

Mirrors the structure of ndvi.py — accepts a multi-band GeoTIFF (or a
pre-computed single-band NDVI raster), analyses the full raster extent,
and returns a per-cell GeoJSON benchmarked against the 30% urban greenery
standard (WHO / C40 Cities guidelines).

No pyproj.Transformer is used anywhere — all coordinate work goes through
rasterio so the bundled PROJ database is used and the EPSG-conflict error
is avoided on systems with multiple PROJ installations.
"""

import os
import json
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import rowcol, xy
from shapely.geometry import box, mapping


from pyproj import datadir

proj_path = datadir.get_data_dir()
os.environ["PROJ_LIB"]  = proj_path
os.environ["PROJ_DATA"] = proj_path


BENCHMARK_PCT = 30.0   # WHO healthy urban greenery standard (%)
VEG_THRESHOLD = 0.2    # NDVI >= this → vegetated pixel


# ── Band helpers ──────────────────────────────────────────────────────────────

def _compute_ndvi(src, red_band, nir_band):
    """Compute NDVI from an open rasterio dataset."""
    red = src.read(red_band).astype("float32")
    nir = src.read(nir_band).astype("float32")
    nodata = src.nodata if src.nodata is not None else 0
    red[red == nodata] = np.nan
    nir[nir == nodata] = np.nan
    denom = nir + red
    return np.where(
        np.isnan(denom) | (denom == 0),
        np.nan,
        (nir - red) / denom,
    ).astype("float32")


def _autodetect_red_nir(src):
    """
    Auto-detect Red and NIR band indices (1-based).

    Priority:
    1. Band description strings (e.g. "red", "nir", "b4", "sr_b5" …)
    2. Exactly 2 bands → (1, 2)
    3. ≥5 bands → Landsat-style (4, 5), verified by NIR > Red sample mean
    4. ≥8 bands → Sentinel-2-style (4, 8)
    5. Brute-force scan: pick the pair where band_j / band_i is largest
    """
    count = src.count

    # 1. Descriptions
    descs = [str(d or "").lower() for d in src.descriptions]
    red_kw = ["red", "b4", "band4", "band_4", "sr_b4", "b04"]
    nir_kw = ["nir", "b5", "band5", "band_5", "sr_b5", "b05", "b8", "band8", "b08"]
    r = next((i + 1 for i, d in enumerate(descs) if any(k in d for k in red_kw)), None)
    n = next((i + 1 for i, d in enumerate(descs) if any(k in d for k in nir_kw)), None)
    if r and n and r != n:
        return r, n

    # 2. Two-band file
    if count == 2:
        return 1, 2

    # 3. Landsat-style
    if count >= 5:
        s_red = np.nanmean(src.read(4).astype("float32")[:50, :50])
        s_nir = np.nanmean(src.read(5).astype("float32")[:50, :50])
        if s_nir >= s_red * 0.8:
            return 4, 5

    # 4. Sentinel-2-style
    if count >= 8:
        return 4, 8

    # 5. Brute-force
    best, best_r = (1, 2), -1.0
    for i in range(1, count + 1):
        for j in range(1, count + 1):
            if i == j:
                continue
            try:
                ri = np.nanmean(src.read(i).astype("float32")[:50, :50])
                rj = np.nanmean(src.read(j).astype("float32")[:50, :50])
                if ri > 0 and rj / ri > best_r:
                    best_r, best = rj / ri, (i, j)
            except Exception:
                continue
    return best


# ── Grid cell sizing ──────────────────────────────────────────────────────────

def _adaptive_cell_size_px(width, height, target_cells=200):
    """
    Return a cell size in *pixels* so the grid has ~target_cells cells.
    Works entirely in pixel space — no CRS/PROJ needed.
    Minimum 5 pixels per side.
    """
    raw = (width * height / target_cells) ** 0.5
    cell_px = max(5, int(round(raw)))
    return cell_px


# ── Reprojection ──────────────────────────────────────────────────────────────

def _ensure_wgs84(src_path, dst_path):
    """
    If the raster is not already EPSG:4326, reproject it.
    Uses only rasterio (bundled PROJ) — no pyproj calls.
    Returns the path to use for further processing.
    """
    with rasterio.open(src_path) as src:
        if src.crs is None:
            # No CRS — assume WGS84 and use as-is
            return src_path
        try:
            epsg = src.crs.to_epsg()
        except Exception:
            epsg = None
        if epsg == 4326:
            return src_path

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
                    resampling=Resampling.bilinear,
                )
    return dst_path


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_vegetation_pct(pct):
    """
    Vegetation % per cell → QoL score 0–100, benchmarked at 30%.

    Tier 4 Excellent : >= 50%  → 75–100
    Tier 3 Good      : 30–50%  → 50– 74  (meets benchmark)
    Tier 2 Poor      : 15–30%  → 25– 49  (below benchmark)
    Tier 1 Bad       :  0–15%  →  0– 24
    """
    if pct is None or np.isnan(pct):
        return None
    p = float(np.clip(pct, 0.0, 100.0))
    if p >= 50:
        return int(np.interp(p, [50, 100], [75, 100]))
    if p >= 30:
        return int(np.interp(p, [30, 50],  [50, 74]))
    if p >= 15:
        return int(np.interp(p, [15, 30],  [25, 49]))
    return int(np.interp(p, [0, 15], [0, 24]))


# ── Main function ─────────────────────────────────────────────────────────────

def calculate_vegetation_density(
    geotiff_path: str,
    ndvi_threshold: float = VEG_THRESHOLD,
    output_path: str = None,
    tmp_dir: str = None,
):
    """
    Analyse vegetation density from a GeoTIFF raster.

    Accepts:
    - A multi-band GeoTIFF (Red + NIR auto-detected), or
    - A pre-computed single-band NDVI raster.

    The full raster extent is analysed. No AOI clipping.

    Parameters
    ----------
    geotiff_path   : path to the GeoTIFF
    ndvi_threshold : NDVI >= this is vegetated (default 0.2)
    output_path    : where to write the per-cell GeoJSON
    tmp_dir        : scratch directory for reprojection temp files

    Returns
    -------
    dict:
        vegetation_pct, benchmark_pct, benchmark_gap, passes_benchmark,
        overall_score, valid_pixels, vegetated_pixels, cell_geojson, cell_size_m
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    scratch = tmp_dir or os.path.dirname(geotiff_path) or "."

    # ── Step 1: ensure WGS84 (rasterio-only, no pyproj) ─────────────────────
    wgs_path = os.path.join(scratch, "_veg_wgs84.tif")
    work_path = _ensure_wgs84(geotiff_path, wgs_path)

    # ── Step 2: read bands and compute NDVI ──────────────────────────────────
    with rasterio.open(work_path) as src:
        band_count    = src.count
        transform     = src.transform
        raster_bounds = src.bounds   # (left, bottom, right, top) in WGS84 degrees
        raster_width  = src.width
        raster_height = src.height

        if band_count == 1:
            data   = src.read(1).astype("float32")
            nodata = src.nodata if src.nodata is not None else -9999
            data[data == nodata] = np.nan
            ndvi = data
        else:
            red_band, nir_band = _autodetect_red_nir(src)
            ndvi = _compute_ndvi(src, red_band, nir_band)

    # ── Step 3: overall stats ────────────────────────────────────────────────
    valid_mask   = ~np.isnan(ndvi)
    valid_pixels = int(valid_mask.sum())
    if valid_pixels == 0:
        raise ValueError("No valid pixels found. Check the raster file.")

    veg_mask   = valid_mask & (ndvi >= ndvi_threshold)
    veg_pixels = int(veg_mask.sum())

    vegetation_pct = veg_pixels / valid_pixels * 100.0
    benchmark_gap  = vegetation_pct - BENCHMARK_PCT
    passes         = vegetation_pct >= BENCHMARK_PCT
    overall_score  = min(100.0, vegetation_pct / BENCHMARK_PCT * 100.0)

    # ── Step 4: per-cell grid (pixel-space, no CRS math) ─────────────────────
    cell_px = _adaptive_cell_size_px(raster_width, raster_height)

    # Approximate cell size in metres for the output metadata
    # 1 degree latitude ≈ 111 000 m; use raster height span / pixel rows
    lat_span_deg = abs(raster_bounds.top - raster_bounds.bottom)
    cell_m = max(100, int(round(lat_span_deg / raster_height * cell_px * 111_000)))

    features = []
    for row_start in range(0, raster_height, cell_px):
        row_end = min(row_start + cell_px, raster_height)
        for col_start in range(0, raster_width, cell_px):
            col_end = min(col_start + cell_px, raster_width)

            cell_ndvi  = ndvi[row_start:row_end, col_start:col_end]
            cell_valid = cell_ndvi[~np.isnan(cell_ndvi)]
            if len(cell_valid) == 0:
                continue

            cell_veg_n   = int((cell_valid >= ndvi_threshold).sum())
            cell_veg_pct = cell_veg_n / len(cell_valid) * 100.0
            cell_score   = _score_vegetation_pct(cell_veg_pct)

            # Convert pixel corners to lon/lat using rasterio (no pyproj)
            left,  bottom = xy(transform, row_end,   col_start, offset="ul")
            right, top    = xy(transform, row_start, col_end,   offset="ul")
            # xy returns (col_coord, row_coord) = (lon, lat) for EPSG:4326
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
                    "vegetation_pct": round(cell_veg_pct, 2),
                    "qol_score":      cell_score,
                    "passes_30pct":   cell_veg_pct >= BENCHMARK_PCT,
                    "cell_cx":        round(cell_cx, 6),
                    "cell_cy":        round(cell_cy, 6),
                    "service":        "vegetation",
                },
            })

    cell_geojson = {
        "type":            "FeatureCollection",
        "features":        features,
        "cell_size_m":     cell_m,
        "vegetation_pct":  round(vegetation_pct, 2),
        "benchmark_pct":   BENCHMARK_PCT,
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(cell_geojson, fh)

    return {
        "vegetation_pct":   round(vegetation_pct, 2),
        "benchmark_pct":    BENCHMARK_PCT,
        "benchmark_gap":    round(benchmark_gap, 2),
        "passes_benchmark": passes,
        "overall_score":    round(overall_score, 2),
        "valid_pixels":     valid_pixels,
        "vegetated_pixels": veg_pixels,
        "cell_geojson":     cell_geojson,
        "cell_size_m":      cell_m,
    }
