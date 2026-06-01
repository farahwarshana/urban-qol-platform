"""
informal_settlement.py
Informal Settlement Pattern Analysis from satellite/aerial imagery.

Detects informal settlement patterns using spatial irregularity metrics —
NOT built-up density. The key distinguishing features of informal settlements
vs. planned urban fabric are:

  1. TEXTURE DISORDER  — informal rooftops produce chaotic, high-variance
     pixel patterns; planned blocks have repetitive, low-variance textures.
     Measured by local coefficient of variation (std / mean).

  2. EDGE FRAGMENTATION — informal areas have many short, disconnected edges
     at random orientations; formal areas have fewer, longer, aligned edges.
     Measured as edge pixel density per cell area.

  3. DIRECTIONAL ANISOTROPY — formal grids have dominant edge directions
     (aligned streets); informal areas have near-uniform angular distribution.
     Measured as 1 - max_directional_energy / mean_directional_energy.

  4. LOCAL ENTROPY — information entropy of the luminance histogram within
     each cell; informal = high entropy (many different tones), formal = lower.

These four metrics are combined into an irregularity score (0–100) where
100 = maximally irregular / informal, 0 = perfectly planned / formal.

No machine learning. No pyproj.Transformer. All coordinate work is done
through rasterio's bundled PROJ database.
"""

import os
import json
import math
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import xy
from scipy import ndimage
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union


# ── Classification thresholds (irregularity score 0–100) ─────────────────────
_LOW_THRESHOLD    = 33   # 0–33  : Low (planned / formal)
_MEDIUM_THRESHOLD = 66   # 34–66 : Medium (mixed)
# 67–100 : High (potential informal patterns)


# ── Reprojection (rasterio-only, bundled PROJ) ────────────────────────────────

def _ensure_wgs84(src_path: str, dst_path: str) -> str:
    """Reproject to EPSG:4326 using rasterio's bundled PROJ. No pyproj calls."""
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


# ── Grayscale conversion ──────────────────────────────────────────────────────

def _to_grayscale(data: np.ndarray) -> np.ndarray:
    """Convert multi-band (B, H, W) or single-band (H, W) to float32 [0,1]."""
    if data.ndim == 3 and data.shape[0] >= 3:
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
        gray = np.zeros_like(gray, dtype="float32")
    return gray


# ── Metric 1: Texture disorder (local coefficient of variation) ───────────────

def _texture_disorder_map(gray: np.ndarray, window: int = 9) -> np.ndarray:
    """
    Local coefficient of variation (std/mean) as a texture disorder proxy.
    High CoV → chaotic, mixed textures (informal rooftops).
    Low CoV  → uniform or repetitive textures (planned blocks / fields).
    Returns array in [0, 1] after global percentile normalisation.
    """
    mean  = ndimage.uniform_filter(gray.astype("float64"), size=window)
    mean2 = ndimage.uniform_filter(gray.astype("float64") ** 2, size=window)
    var   = np.maximum(mean2 - mean ** 2, 0.0)
    std   = np.sqrt(var)
    # CoV = std / (mean + epsilon)   — higher where texture is chaotic
    cov   = std / (mean + 1e-6)
    # Normalise to [0, 1] using 2nd–98th percentile to avoid outlier stretch
    p2, p98 = np.percentile(cov, 2), np.percentile(cov, 98)
    if p98 > p2:
        cov = np.clip((cov - p2) / (p98 - p2), 0.0, 1.0)
    else:
        cov = np.zeros_like(gray)
    return cov.astype("float32")


# ── Metric 2: Edge fragmentation ─────────────────────────────────────────────

def _edge_fragmentation_map(gray: np.ndarray) -> np.ndarray:
    """
    Sobel edge magnitude normalised to [0, 1].
    High edge density per cell = many short edges = fragmented = informal.
    Low edge density = clear, sparse edges = formal grid.
    Normalised globally by 98th percentile to suppress extreme outliers.
    """
    gx  = ndimage.sobel(gray.astype("float64"), axis=1)
    gy  = ndimage.sobel(gray.astype("float64"), axis=0)
    mag = np.hypot(gx, gy)
    p98 = np.percentile(mag, 98)
    if p98 > 0:
        mag = np.clip(mag / p98, 0.0, 1.0)
    return mag.astype("float32")


# ── Metric 3: Directional anisotropy ─────────────────────────────────────────

def _anisotropy_map(gray: np.ndarray, n_angles: int = 8) -> np.ndarray:
    """
    Measures how uniformly distributed edge directions are in a local window.
    Formal areas: dominant direction (street grid) → low entropy → low anisotropy.
    Informal areas: random edge directions → high entropy → high anisotropy.

    Returns array in [0, 1]:  1 = fully isotropic (informal), 0 = anisotropic (formal).
    """
    angles = np.linspace(0, np.pi, n_angles, endpoint=False)
    # Directional derivative at each angle using Sobel-like kernels
    direction_responses = []
    for theta in angles:
        kx = np.cos(theta)
        ky = np.sin(theta)
        gx = ndimage.sobel(gray.astype("float64"), axis=1)
        gy = ndimage.sobel(gray.astype("float64"), axis=0)
        response = np.abs(kx * gx + ky * gy)
        direction_responses.append(response)

    # Stack into (n_angles, H, W)
    stack = np.stack(direction_responses, axis=0)  # (n_angles, H, W)

    # Per pixel, normalise responses to a probability distribution
    total = stack.sum(axis=0) + 1e-10  # (H, W)
    p     = stack / total              # (n_angles, H, W)

    # Shannon entropy across directions: high entropy = isotropic = informal
    entropy = -np.sum(p * np.log(p + 1e-10), axis=0)  # (H, W)
    max_entropy = math.log(n_angles)

    # Normalise to [0, 1]
    anisotropy = np.clip(entropy / max_entropy, 0.0, 1.0).astype("float32")

    # Smooth slightly so per-cell aggregation is stable
    anisotropy = ndimage.uniform_filter(anisotropy, size=7)
    return anisotropy.astype("float32")


# ── Metric 4: Local entropy ───────────────────────────────────────────────────

def _local_entropy_map(gray: np.ndarray, window: int = 11) -> np.ndarray:
    """
    Approximate per-pixel local Shannon entropy using quantised intensity.
    Informal areas: many different roof materials / colours → high entropy.
    Formal areas:  repetitive rooftops / pavement → lower entropy.

    Uses 16-level quantisation for speed. Returns array in [0, 1].
    """
    # Quantise to 16 levels
    q = (np.clip(gray, 0.0, 1.0) * 15).astype(np.uint8)
    max_e = math.log(16)
    out   = np.zeros_like(gray, dtype="float32")

    # Compute entropy for each level using sliding window sums
    level_maps = []
    for level in range(16):
        indicator = (q == level).astype("float32")
        count     = ndimage.uniform_filter(indicator, size=window) * (window ** 2)
        level_maps.append(count)

    total = np.array(level_maps).sum(axis=0) + 1e-10
    for level_count in level_maps:
        p    = level_count / total
        safe = np.where(p > 1e-12, p, 1.0)  # avoid log(0)
        out -= np.where(p > 1e-12, p * np.log(safe), 0.0)

    out = np.clip(out / max_e, 0.0, 1.0)
    return out.astype("float32")


# ── Cell sizing ───────────────────────────────────────────────────────────────

def _adaptive_cell_size_px(width: int, height: int, target_cells: int = 400) -> int:
    """Return cell size in pixels so grid has ~target_cells cells."""
    raw = (width * height / target_cells) ** 0.5
    return max(8, int(round(raw)))


# ── Irregularity score ────────────────────────────────────────────────────────

def _irregularity_score(tex: float, edge: float, aniso: float, entropy: float) -> int:
    """
    Weighted combination of four irregularity metrics → score 0–100.
    All inputs are in [0, 1]; higher = more irregular.

    Weights reflect diagnostic value for informal settlement detection:
      Texture disorder  0.30  — chaotic roof pixel patterns
      Edge fragmentation 0.25  — many short disconnected edges
      Directional anisotropy 0.25  — no dominant street direction
      Local entropy     0.20  — high spectral diversity
    """
    raw = 0.30 * tex + 0.25 * edge + 0.25 * aniso + 0.20 * entropy
    return int(round(float(np.clip(raw * 100.0, 0.0, 100.0))))


def _classify(score: int) -> str:
    if score is None:
        return "unknown"
    if score <= _LOW_THRESHOLD:
        return "low"
    if score <= _MEDIUM_THRESHOLD:
        return "medium"
    return "high"


def _score_to_qol(score) -> int:
    """
    Irregularity score (0=planned→good, 100=informal→bad) → QoL (0–100).
    Tier 4 Excellent (75–100): irregularity 0–15
    Tier 3 Good      (50– 74): irregularity 16–33
    Tier 2 Poor      (25– 49): irregularity 34–66
    Tier 1 Bad       ( 0– 24): irregularity 67–100
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
    1.  Preprocess: grayscale conversion + normalisation to [0,1].
    2.  Compute texture disorder map (local CoV).
    3.  Compute edge fragmentation map (Sobel magnitude density).
    4.  Compute directional anisotropy map (edge direction entropy).
    5.  Compute local entropy map (spectral diversity).
    6.  Divide raster extent into adaptive grid (~400 cells).
    7.  Per cell: average each metric map over the cell pixels.
    8.  Combine into irregularity score (0–100).
    9.  Classify: Low (planned) / Medium / High (informal).
    10. Merge high-irregularity cells into zone polygons.

    Returns
    -------
    dict: avg_irregularity, high_pct, medium_pct, low_pct,
          overall_qol_score, cell_size_m, high_zone_count,
          cell_geojson, high_zones_geojson, combined_geojson
    """
    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    scratch = tmp_dir or os.path.dirname(geotiff_path) or "."

    # ── Step 1: ensure WGS84 (rasterio-only, no external pyproj calls) ─────
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

    if nodata is not None:
        data[data == nodata] = np.nan

    # ── Step 1 cont.: grayscale + normalise ────────────────────────────────
    gray = _to_grayscale(data)
    # Fill NaN with median so filter kernels don't propagate NaN
    finite_vals = gray[np.isfinite(gray)]
    fill_val    = float(np.median(finite_vals)) if len(finite_vals) > 0 else 0.5
    gray        = np.where(np.isfinite(gray), gray, fill_val)

    # ── Steps 2–5: compute metric maps over full raster ────────────────────
    tex_map      = _texture_disorder_map(gray)
    edge_map     = _edge_fragmentation_map(gray)
    aniso_map    = _anisotropy_map(gray)
    entropy_map  = _local_entropy_map(gray)

    # ── Step 6: adaptive grid ──────────────────────────────────────────────
    cell_px = _adaptive_cell_size_px(raster_width, raster_height)

    lat_span_deg = abs(raster_bounds.top - raster_bounds.bottom)
    cell_m = max(50, int(round(lat_span_deg / raster_height * cell_px * 111_000)))

    # ── Steps 7–9: per-cell aggregation + scoring ──────────────────────────
    features    = []

    for row_start in range(0, raster_height, cell_px):
        row_end = min(row_start + cell_px, raster_height)
        for col_start in range(0, raster_width, cell_px):
            col_end = min(col_start + cell_px, raster_width)

            # Use original gray to find valid pixels (nodata was NaN before fill)
            cell_orig = data if data.ndim == 2 else data[0]
            # Actually use gray (already filled) for metric slices
            cell_tex  = tex_map[row_start:row_end, col_start:col_end]
            cell_edge = edge_map[row_start:row_end, col_start:col_end]
            cell_aniso = aniso_map[row_start:row_end, col_start:col_end]
            cell_entr = entropy_map[row_start:row_end, col_start:col_end]

            n_px = cell_tex.size
            if n_px == 0:
                continue

            tex_val   = float(np.mean(cell_tex))
            edge_val  = float(np.mean(cell_edge))
            aniso_val = float(np.mean(cell_aniso))
            entr_val  = float(np.mean(cell_entr))

            irr_score = _irregularity_score(tex_val, edge_val, aniso_val, entr_val)
            label     = _classify(irr_score)
            qol_score = _score_to_qol(irr_score)

            # Pixel corners → lon/lat via rasterio transform (no pyproj)
            left,  bottom = xy(transform, row_end,   col_start, offset="ul")
            right, top    = xy(transform, row_start, col_end,   offset="ul")

            lon_min = min(left,   right)
            lon_max = max(left,   right)
            lat_min = min(bottom, top)
            lat_max = max(bottom, top)

            features.append({
                "type": "Feature",
                "geometry": mapping(box(lon_min, lat_min, lon_max, lat_max)),
                "properties": {
                    "irregularity_score": irr_score,
                    "classification":     label,
                    "qol_score":          qol_score,
                    "texture_disorder":   round(tex_val,   4),
                    "edge_fragmentation": round(edge_val,  4),
                    "directional_anisotropy": round(aniso_val, 4),
                    "local_entropy":      round(entr_val,  4),
                    "cell_cx":            round((lon_min + lon_max) / 2, 6),
                    "cell_cy":            round((lat_min + lat_max) / 2, 6),
                    "service":            "informal-settlement",
                },
            })

    if not features:
        raise ValueError("No valid cells produced. Check that the raster contains data.")

    # ── Overall stats ──────────────────────────────────────────────────────
    all_scores = [f["properties"]["irregularity_score"] for f in features]
    avg_irr    = round(float(np.mean(all_scores)), 2)
    high_n     = sum(1 for f in features if f["properties"]["classification"] == "high")
    med_n      = sum(1 for f in features if f["properties"]["classification"] == "medium")
    low_n      = sum(1 for f in features if f["properties"]["classification"] == "low")
    total_n    = len(features)

    high_pct   = round(high_n / total_n * 100, 2)
    medium_pct = round(med_n  / total_n * 100, 2)
    low_pct    = round(low_n  / total_n * 100, 2)
    overall_qol = _score_to_qol(int(avg_irr))

    # ── Step 10: merge high-irregularity cells into zone polygons ──────────
    high_geoms = [
        shape(f["geometry"])
        for f in features if f["properties"]["classification"] == "high"
    ]

    high_zone_features = []
    if high_geoms:
        merged     = unary_union(high_geoms)
        geoms_list = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
        for g in geoms_list:
            if not g.is_empty:
                high_zone_features.append({
                    "type": "Feature",
                    "geometry": mapping(g),
                    "properties": {
                        "type":    "high_irregularity_zone",
                        "service": "informal-settlement",
                    },
                })

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
        "avg_irregularity":  avg_irr,
        "high_pct":          high_pct,
        "medium_pct":        medium_pct,
        "low_pct":           low_pct,
        "overall_qol_score": overall_qol,
        "cell_size_m":       cell_m,
        "high_zone_count":   len(high_zone_features),
        "cell_geojson": {
            "type": "FeatureCollection", "features": features,
            "cell_size_m": cell_m, "avg_irregularity": avg_irr,
        },
        "high_zones_geojson": {
            "type": "FeatureCollection", "features": high_zone_features,
        },
        "combined_geojson": combined,
    }
