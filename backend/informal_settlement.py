"""
informal_settlement.py
Informal Settlement Pattern Analysis from satellite/aerial imagery.

Analyses a GeoTIFF raster to detect informal settlement patterns using
texture irregularity, edge density, and built-up crowding metrics.
No machine learning — pure raster processing only.

Returns per-cell scores and merged high-irregularity polygons.
"""

import os
import json
import math
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import xy
from rasterio.features import shapes as rasterio_shapes
from scipy import ndimage
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union


# ── Classification thresholds ─────────────────────────────────────────────────

# Irregularity score per cell (0–100): high = informal / unplanned
_LOW_THRESHOLD    = 33   # 0–33  : Low  (planned)
_MEDIUM_THRESHOLD = 66   # 34–66 : Medium
# 67–100 : High (potential informal patterns)


# ── Reprojection ──────────────────────────────────────────────────────────────

def _ensure_wgs84(src_path, dst_path):
    """Reproject raster to EPSG:4326 using only rasterio (bundled PROJ)."""
    with rasterio.open(src_path) as src:
        if src.crs is None:
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


# ── Preprocessing ─────────────────────────────────────────────────────────────

def _to_grayscale(data):
    """
    Convert multi-band array (bands, H, W) or single-band (H, W) to float32
    grayscale [0.0, 1.0].
    """
    if data.ndim == 3 and data.shape[0] >= 3:
        # Use luminance weights on first three bands
        gray = (0.2989 * data[0].astype("float32") +
                0.5870 * data[1].astype("float32") +
                0.1140 * data[2].astype("float32"))
    elif data.ndim == 3:
        gray = data[0].astype("float32")
    else:
        gray = data.astype("float32")

    mn, mx = np.nanmin(gray), np.nanmax(gray)
    if mx > mn:
        gray = (gray - mn) / (mx - mn)
    else:
        gray = np.zeros_like(gray)
    return gray


# ── Texture irregularity (local variance) ────────────────────────────────────

def _local_variance(gray, window=7):
    """Compute per-pixel local variance using a square sliding window."""
    mean  = ndimage.uniform_filter(gray,  size=window)
    mean2 = ndimage.uniform_filter(gray ** 2, size=window)
    var   = np.maximum(mean2 - mean ** 2, 0.0)
    return var


# ── Edge density ──────────────────────────────────────────────────────────────

def _edge_map(gray):
    """Sobel-based edge detection — returns edge magnitude image [0, 1]."""
    gx = ndimage.sobel(gray, axis=1)
    gy = ndimage.sobel(gray, axis=0)
    mag = np.hypot(gx, gy)
    mx = mag.max()
    if mx > 0:
        mag /= mx
    return mag.astype("float32")


# ── Built-up crowding (Otsu-style threshold) ──────────────────────────────────

def _buildup_mask(gray):
    """
    Simple Otsu-like thresholding to classify built-up pixels.
    Built-up pixels tend to be brighter in panchromatic / near-IR composites.
    Returns a float32 mask [0, 1] where 1 = built-up.
    """
    finite = gray[np.isfinite(gray)]
    if len(finite) == 0:
        return np.zeros_like(gray)

    # Otsu threshold via histogram
    hist, bin_edges = np.histogram(finite, bins=256)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    total = hist.sum()
    if total == 0:
        return np.zeros_like(gray)

    w0 = np.cumsum(hist) / total
    w1 = 1.0 - w0
    mu0 = np.cumsum(hist * bin_centers) / (np.cumsum(hist) + 1e-10)
    mu_total = (hist * bin_centers).sum() / total
    mu1 = np.where(w1 > 0, (mu_total - w0 * mu0) / (w1 + 1e-10), 0.0)

    sigma_b = w0 * w1 * (mu0 - mu1) ** 2
    best_bin = int(np.argmax(sigma_b))
    threshold = bin_centers[best_bin]

    return (gray >= threshold).astype("float32")


# ── Adaptive cell size ────────────────────────────────────────────────────────

def _adaptive_cell_size_px(width, height, target_cells=400):
    """Return cell size in pixels so the grid has ~target_cells cells."""
    raw = (width * height / target_cells) ** 0.5
    return max(5, int(round(raw)))


# ── Irregularity score ────────────────────────────────────────────────────────

def _irregularity_score(tex_val, edge_val, buildup_val, w_tex=0.40, w_edge=0.35, w_bup=0.25):
    """
    Combine normalised texture, edge density, and built-up ratio into a
    0–100 irregularity score. Higher = more irregular / potentially informal.
    """
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (tex_val, edge_val, buildup_val)):
        return None
    raw = w_tex * tex_val + w_edge * edge_val + w_bup * buildup_val
    return int(round(float(np.clip(raw * 100.0, 0.0, 100.0))))


def _classify(score):
    """Return classification label from irregularity score."""
    if score is None:
        return "unknown"
    if score <= _LOW_THRESHOLD:
        return "low"
    if score <= _MEDIUM_THRESHOLD:
        return "medium"
    return "high"


def _score_to_qol(score):
    """
    Convert irregularity score (0=planned, 100=informal) to QoL score
    (0=bad, 100=good).  High irregularity → low QoL.

    Tier 4 Excellent (QoL 75–100): irregularity  0–15  (very planned)
    Tier 3 Good      (QoL 50– 74): irregularity 16–33
    Tier 2 Poor      (QoL 25– 49): irregularity 34–66
    Tier 1 Bad       (QoL  0– 24): irregularity 67–100 (informal)
    """
    if score is None:
        return None
    s = int(np.clip(score, 0, 100))
    if s <= 15:
        return int(np.interp(s, [0,  15],  [100, 75]))
    if s <= 33:
        return int(np.interp(s, [15, 33],  [74,  50]))
    if s <= 66:
        return int(np.interp(s, [33, 66],  [49,  25]))
    return int(np.interp(s, [66, 100], [24,   0]))


# ── Main function ─────────────────────────────────────────────────────────────

def calculate_informal_settlement(
    geotiff_path: str,
    output_path: str = None,
    tmp_dir: str = None,
):
    """
    Analyse informal settlement patterns from a satellite/aerial GeoTIFF.

    Steps
    -----
    1. Preprocess raster (grayscale, normalise).
    2. Compute texture irregularity (local variance).
    3. Detect edges and compute edge magnitude image.
    4. Estimate built-up crowding via Otsu thresholding.
    5. Divide extent into adaptive grid.
    6. Per cell: texture irregularity, edge density, built-up ratio.
    7. Combine into irregularity score (0–100).
    8. Classify: low (planned) / medium / high (informal).
    9. Extract and merge high-irregularity cells into polygons.

    Returns
    -------
    dict with keys:
        avg_irregularity, high_pct, medium_pct, low_pct,
        overall_qol_score, cell_size_m, high_zone_count,
        cell_geojson, high_zones_geojson
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    scratch = tmp_dir or os.path.dirname(geotiff_path) or "."

    # ── Step 1: ensure WGS84 ────────────────────────────────────────────────
    wgs_path  = os.path.join(scratch, "_ispa_wgs84.tif")
    work_path = _ensure_wgs84(geotiff_path, wgs_path)

    with rasterio.open(work_path) as src:
        raster_bounds = src.bounds
        raster_width  = src.width
        raster_height = src.height
        transform     = src.transform
        nodata        = src.nodata

        if src.count >= 3:
            data = src.read([1, 2, 3]).astype("float32")
        else:
            data = src.read(1).astype("float32")

    # Replace nodata with nan
    if nodata is not None:
        if data.ndim == 3:
            data[data == nodata] = np.nan
        else:
            data[data == nodata] = np.nan

    # ── Step 1 cont.: grayscale + normalise ────────────────────────────────
    gray = _to_grayscale(data)
    gray[~np.isfinite(gray)] = np.nanmedian(gray[np.isfinite(gray)]) if np.any(np.isfinite(gray)) else 0.0

    # ── Step 2: texture irregularity map ───────────────────────────────────
    tex_map = _local_variance(gray)
    tex_max = tex_map.max()
    tex_norm = (tex_map / tex_max) if tex_max > 0 else tex_map

    # ── Step 3: edge density map ────────────────────────────────────────────
    edge_map = _edge_map(gray)

    # ── Step 4: built-up crowding mask ─────────────────────────────────────
    buildup_mask = _buildup_mask(gray)

    # ── Step 5: adaptive grid ───────────────────────────────────────────────
    cell_px = _adaptive_cell_size_px(raster_width, raster_height)

    lat_span_deg = abs(raster_bounds.top - raster_bounds.bottom)
    cell_m = max(50, int(round(lat_span_deg / raster_height * cell_px * 111_000)))

    # ── Steps 6–8: per-cell metrics & scores ───────────────────────────────
    features = []
    high_scores = []

    for row_start in range(0, raster_height, cell_px):
        row_end = min(row_start + cell_px, raster_height)
        for col_start in range(0, raster_width, cell_px):
            col_end = min(col_start + cell_px, raster_width)

            cell_gray   = gray[row_start:row_end, col_start:col_end]
            cell_tex    = tex_norm[row_start:row_end, col_start:col_end]
            cell_edge   = edge_map[row_start:row_end, col_start:col_end]
            cell_buildup = buildup_mask[row_start:row_end, col_start:col_end]

            valid = np.isfinite(cell_gray)
            n_valid = int(valid.sum())
            if n_valid == 0:
                continue

            tex_val     = float(np.mean(cell_tex[valid]))
            edge_val    = float(np.mean(cell_edge[valid]))
            buildup_val = float(np.mean(cell_buildup[valid]))

            irr_score   = _irregularity_score(tex_val, edge_val, buildup_val)
            label       = _classify(irr_score)
            qol_score   = _score_to_qol(irr_score)

            # Convert pixel corners to lon/lat
            left,  bottom = xy(transform, row_end,   col_start, offset="ul")
            right, top    = xy(transform, row_start, col_end,   offset="ul")

            cell_lon_min = min(left, right)
            cell_lon_max = max(left, right)
            cell_lat_min = min(bottom, top)
            cell_lat_max = max(bottom, top)
            cell_cx = (cell_lon_min + cell_lon_max) / 2
            cell_cy = (cell_lat_min + cell_lat_max) / 2

            feat = {
                "type": "Feature",
                "geometry": mapping(box(cell_lon_min, cell_lat_min, cell_lon_max, cell_lat_max)),
                "properties": {
                    "irregularity_score": irr_score,
                    "classification":     label,
                    "qol_score":          qol_score,
                    "texture_val":        round(tex_val, 4),
                    "edge_val":           round(edge_val, 4),
                    "buildup_ratio":      round(buildup_val, 4),
                    "cell_cx":            round(cell_cx, 6),
                    "cell_cy":            round(cell_cy, 6),
                    "service":            "informal-settlement",
                },
            }
            features.append(feat)

            if label == "high":
                high_scores.append(irr_score)

    if not features:
        raise ValueError("No valid cells produced. Check that the raster contains data.")

    # ── Overall stats ────────────────────────────────────────────────────────
    all_scores = [f["properties"]["irregularity_score"] for f in features if f["properties"]["irregularity_score"] is not None]
    avg_irr  = round(float(np.mean(all_scores)), 2) if all_scores else 0.0
    high_n   = sum(1 for f in features if f["properties"]["classification"] == "high")
    med_n    = sum(1 for f in features if f["properties"]["classification"] == "medium")
    low_n    = sum(1 for f in features if f["properties"]["classification"] == "low")
    total_n  = len(features)

    high_pct   = round(high_n / total_n * 100, 2) if total_n else 0.0
    medium_pct = round(med_n  / total_n * 100, 2) if total_n else 0.0
    low_pct    = round(low_n  / total_n * 100, 2) if total_n else 0.0

    overall_qol = _score_to_qol(int(avg_irr))

    # ── Step 9: merge high-irregularity cells into polygons ─────────────────
    high_geoms = [
        shape(f["geometry"])
        for f in features
        if f["properties"]["classification"] == "high"
    ]

    high_zone_features = []
    if high_geoms:
        merged = unary_union(high_geoms)
        geoms_list = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for g in geoms_list:
            if g.is_empty:
                continue
            high_zone_features.append({
                "type": "Feature",
                "geometry": mapping(g),
                "properties": {
                    "type":    "high_irregularity_zone",
                    "service": "informal-settlement",
                },
            })

    cell_geojson = {
        "type":             "FeatureCollection",
        "features":         features,
        "cell_size_m":      cell_m,
        "avg_irregularity": avg_irr,
        "high_pct":         high_pct,
        "medium_pct":       medium_pct,
        "low_pct":          low_pct,
    }

    high_zones_geojson = {
        "type":     "FeatureCollection",
        "features": high_zone_features,
    }

    # ── Combined output (cells + high zones) ───────────────────────────────
    combined = {
        "type":     "FeatureCollection",
        "features": features + high_zone_features,
        "cell_size_m":      cell_m,
        "avg_irregularity": avg_irr,
        "high_pct":         high_pct,
        "medium_pct":       medium_pct,
        "low_pct":          low_pct,
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(combined, fh)

    return {
        "avg_irregularity": avg_irr,
        "high_pct":         high_pct,
        "medium_pct":       medium_pct,
        "low_pct":          low_pct,
        "overall_qol_score": overall_qol,
        "cell_size_m":      cell_m,
        "high_zone_count":  len(high_zone_features),
        "cell_geojson":     cell_geojson,
        "high_zones_geojson": high_zones_geojson,
        "combined_geojson": combined,
    }
