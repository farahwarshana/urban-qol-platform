import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask

def _detect_bands(src):
    """
    Infer Red and NIR band indices and satellite label from the rasterio dataset.

    Returns a dict:
      red_index   : 1-based band index used for Red
      nir_index   : 1-based band index used for NIR
      red_name    : human label, e.g. "Band 3 (B3)"
      nir_name    : human label, e.g. "Band 4 (B4)"
      satellite   : display string, e.g. "Landsat 8/9" or "Unknown (4-band subset)"
    """
    tags = {k.lower(): v.lower() for k, v in (src.tags() or {}).items()}
    n = src.count
    descriptions = src.descriptions or []

    # Normalised band name list (uppercase, stripped), e.g. ["B2","B3","B4","B8"]
    desc_names = [d.strip().upper() if d else "" for d in descriptions]

    def band_label(idx):
        # idx is 1-based
        name = desc_names[idx - 1] if idx - 1 < len(desc_names) and desc_names[idx - 1] else f"B{idx}"
        return f"Band {idx} ({name})"

    def _find_band(candidates):
        """Return 1-based index of first description matching any candidate name, or None."""
        for name in candidates:
            if name in desc_names:
                return desc_names.index(name) + 1
        return None

    # ── 1. Metadata tags (most reliable) ─────────────────────────────────────
    spacecraft_tag = (
        tags.get("spacecraft_id", "")
        or tags.get("satellite", "")
        or tags.get("mission", "")
    )

    if "sentinel" in spacecraft_tag:
        red_i = _find_band(["B4"]) or 4
        nir_i = _find_band(["B8", "B8A"]) or 8
        satellite = "Sentinel-2"
    elif "landsat" in spacecraft_tag:
        if n == 7:
            red_i = _find_band(["B3", "SR_B3"]) or 3
            nir_i = _find_band(["B4", "SR_B4"]) or 4
            satellite = "Landsat 4–7 (TM/ETM+)"
        else:
            red_i = _find_band(["B4", "SR_B4"]) or 4
            nir_i = _find_band(["B5", "SR_B5"]) or 5
            sat_id = spacecraft_tag.replace("landsat_", "Landsat ").replace("landsat", "Landsat")
            satellite = sat_id.title() if sat_id else "Landsat 8/9"

    # ── 2. Band description names (subset / clipped images) ──────────────────
    elif _find_band(["B8", "B8A"]) is not None:
        # Sentinel-2 NIR band names present in descriptions
        red_i = _find_band(["B4"]) or 3
        nir_i = _find_band(["B8", "B8A"])
        satellite = "Sentinel-2 (from band names)"
    elif _find_band(["SR_B4", "SR_B5"]) is not None:
        red_i = _find_band(["SR_B4"]) or 4
        nir_i = _find_band(["SR_B5"]) or 5
        satellite = "Landsat 8/9 (from band names)"
    elif _find_band(["SR_B3", "SR_B4"]) is not None:
        red_i = _find_band(["SR_B3"]) or 3
        nir_i = _find_band(["SR_B4"]) or 4
        satellite = "Landsat 4–7 (from band names)"

    # ── 3. Band count heuristic (last resort) ─────────────────────────────────
    elif n == 2:
        red_i, nir_i = 1, 2
        satellite = "Unknown (pre-extracted Red+NIR)"
    elif n == 4:
        red_i, nir_i = 3, 4
        satellite = "Unknown (4-band BGRN subset)"
    elif n == 7:
        red_i, nir_i = 3, 4
        satellite = "Landsat 4–7 (TM/ETM+, inferred)"
    elif n == 13:
        red_i, nir_i = 4, 8
        satellite = "Sentinel-2 (inferred)"
    else:
        red_i, nir_i = 4, 5
        satellite = "Landsat 8/9 (inferred)"

    return {
        "red_index": red_i,
        "nir_index": nir_i,
        "red_name":  band_label(red_i),
        "nir_name":  band_label(nir_i),
        "satellite": satellite,
    }


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
        detected = _detect_bands(src)
        red_band_index = detected["red_index"]
        nir_band_index = detected["nir_index"]

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
    stats = {
        "output_path": output_ndvi_path,
        "valid_pixels": int(valid_ndvi.size),
        "red_band":  detected["red_name"],
        "nir_band":  detected["nir_name"],
        "satellite": detected["satellite"],
    }

    if valid_ndvi.size > 0:
        stats.update({
            "min":  float(np.nanmin(valid_ndvi)),
            "max":  float(np.nanmax(valid_ndvi)),
            "mean": float(np.nanmean(valid_ndvi)),
        })
    else:
        stats["warning"] = "No valid NDVI pixels found."

    return stats

