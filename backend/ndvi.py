import os
import numpy as np
import rasterio
from rasterio import crs
from rasterio.warp import calculate_default_transform, reproject, Resampling
import geopandas as gpd
from rasterio.mask import mask


# def calculate_ndvi_from_bands(geotiff_path, red_band_index, nir_band_index, output_ndvi_path):
#     """
#     Extract Red and NIR bands from a single multi-band GeoTIFF and compute NDVI.

#     Parameters
#     ----------
#     geotiff_path     : path to the multi-band Landsat GeoTIFF
#     red_band_index   : band number for Red (Landsat 8/9 = 4)
#     nir_band_index   : band number for NIR (Landsat 8/9 = 5)
#     output_ndvi_path : where to write the output NDVI GeoTIFF
#     """
#     if not os.path.exists(geotiff_path):
#         raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

#     with rasterio.open(geotiff_path) as src:
#         band_count = src.count
#         if red_band_index > band_count or nir_band_index > band_count:
#             raise ValueError(
#                 f"File has {band_count} band(s) but band indices "
#                 f"{red_band_index} (Red) and {nir_band_index} (NIR) were requested."
#             )

#         red = src.read(red_band_index).astype("float32")
#         nir = src.read(nir_band_index).astype("float32")
#         meta = src.meta.copy()
        
#         # Ensure CRS is preserved
#         if src.crs:
#             meta["crs"] = src.crs

#     # Treat zero pixels as NoData
#     red[red == 0] = np.nan
#     nir[nir == 0] = np.nan

#     denominator = nir + red

#     ndvi = np.where(
#         np.isnan(denominator) | (denominator == 0),
#         np.nan,
#         (nir - red) / denominator,
#     ).astype("float32")

#     meta.update({
#         "driver": "GTiff",
#         "count":  1,
#         "dtype":  "float32",
#         "nodata": -9999,
#         "crs": rasterio.crs.CRS.from_epsg(4326),  # Set WGS84 CRS for Leaflet compatibility
#     })

#     ndvi_output = np.where(np.isnan(ndvi), -9999, ndvi).astype("float32")

#     output_dir = os.path.dirname(output_ndvi_path)
#     if output_dir:
#         os.makedirs(output_dir, exist_ok=True)

#     with rasterio.open(output_ndvi_path, "w", **meta) as dst:
#         dst.write(ndvi_output, 1)
    
#     print(f"NDVI output saved with WGS84 (EPSG:4326) CRS")

#     valid_ndvi = ndvi[~np.isnan(ndvi)]
#     stats = {"output_path": output_ndvi_path, "valid_pixels": int(valid_ndvi.size)}

#     if valid_ndvi.size > 0:
#         stats.update({
#             "min":  float(np.nanmin(valid_ndvi)),
#             "max":  float(np.nanmax(valid_ndvi)),
#             "mean": float(np.nanmean(valid_ndvi)),
#         })
#     else:
#         stats["warning"] = "No valid NDVI pixels found."

#     return stats



import os
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask


def calculate_ndvi_from_bands(geotiff_path, red_band_index, nir_band_index, output_ndvi_path):
    """
    Extract Red and NIR bands from a single multi-band GeoTIFF, compute NDVI,
    and write the output with a clean EPSG:4326 CRS tag for Leaflet/georaster.

    If the source is already in EPSG:4326 the pixels are written as-is.
    If the source is in a different CRS (e.g. UTM) the raster is reprojected.

    Parameters
    ----------
    geotiff_path     : path to the multi-band Landsat GeoTIFF
    red_band_index   : band number for Red (Landsat 8/9 = 4)
    nir_band_index   : band number for NIR (Landsat 8/9 = 5)
    output_ndvi_path : where to write the output NDVI GeoTIFF
    """
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    if not os.path.exists(geotiff_path):
        raise FileNotFoundError(f"GeoTIFF not found: {geotiff_path}")

    # Always write this authority string — georaster needs "EPSG:4326" explicitly
    TARGET_CRS = "EPSG:4326"

    NODATA = -9999.0

    with rasterio.open(geotiff_path) as src:
        band_count = src.count
        if red_band_index > band_count or nir_band_index > band_count:
            raise ValueError(
                f"File has {band_count} band(s) but band indices "
                f"{red_band_index} (Red) and {nir_band_index} (NIR) were requested."
            )

        red = src.read(red_band_index).astype("float32")
        nir = src.read(nir_band_index).astype("float32")
        src_transform = src.transform
        src_height, src_width = src.height, src.width

        # Determine the actual source CRS
        src_crs = src.crs
        src_epsg = src_crs.to_epsg() if src_crs else None
        print(f"Source CRS: {src_crs}  |  EPSG: {src_epsg}")

    # ── Compute NDVI ──────────────────────────────────────────────────────────
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan

    denominator = nir + red
    ndvi = np.where(
        np.isnan(denominator) | (denominator == 0),
        np.nan,
        (nir - red) / denominator,
    ).astype("float32")

    ndvi_filled = np.where(np.isnan(ndvi), NODATA, ndvi).astype("float32")

    output_dir = os.path.dirname(output_ndvi_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # ── Write output ──────────────────────────────────────────────────────────
    needs_reproject = src_crs is not None and src_epsg != 4326

    if needs_reproject:
        # Reproject pixel data AND assign clean EPSG:4326 tag
        print(f"Reprojecting from EPSG:{src_epsg} → EPSG:4326")
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_crs, TARGET_CRS, src_width, src_height, transform=src_transform
        )
        dst_meta = {
            "driver":    "GTiff",
            "count":     1,
            "dtype":     "float32",
            "nodata":    NODATA,
            "crs":       TARGET_CRS,
            "transform": dst_transform,
            "width":     dst_width,
            "height":    dst_height,
        }
        with rasterio.open(output_ndvi_path, "w", **dst_meta) as dst:
            reproject(
                source        = ndvi_filled,
                destination   = rasterio.band(dst, 1),
                src_transform = src_transform,
                src_crs       = src_crs,
                dst_transform = dst_transform,
                dst_crs       = TARGET_CRS,
                src_nodata    = NODATA,
                dst_nodata    = NODATA,
                resampling    = Resampling.bilinear,
            )
    else:
        # Already in 4326 (or no CRS) — write pixels as-is but stamp EPSG:4326
        print("Source is already EPSG:4326 — writing with explicit CRS tag")
        dst_meta = {
            "driver":    "GTiff",
            "count":     1,
            "dtype":     "float32",
            "nodata":    NODATA,
            "crs":       TARGET_CRS,   # explicit "EPSG:4326" string, not a WKT blob
            "transform": src_transform,
            "width":     src_width,
            "height":    src_height,
        }
        with rasterio.open(output_ndvi_path, "w", **dst_meta) as dst:
            dst.write(ndvi_filled, 1)

    print(f"NDVI saved → {output_ndvi_path}  (CRS: {TARGET_CRS})")

    # ── Stats ─────────────────────────────────────────────────────────────────
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


def calculate_ndvi(red_band_path, nir_band_path, aoi_path, output_ndvi_path):
    """
    Calculate NDVI from Landsat Red and NIR bands clipped to AOI.

    Landsat 8/9:
    Red = SR_B4
    NIR = SR_B5

    NDVI = (NIR - RED) / (NIR + RED)
    """

    # Check input files
    for path in [red_band_path, nir_band_path, aoi_path]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

    # Read AOI
    aoi = gpd.read_file(aoi_path)

    if aoi.empty:
        raise ValueError("AOI file is empty.")

    if aoi.crs is None:
        raise ValueError("AOI has no CRS. Make sure the .prj file exists for the shapefile.")

    # Open Red band
    with rasterio.open(red_band_path) as red_src:
        raster_crs = red_src.crs

        if raster_crs is None:
            raise ValueError("Red raster has no CRS.")

        # Reproject AOI to raster CRS
        if aoi.crs != raster_crs:
            aoi = aoi.to_crs(raster_crs)

        geometries = [geom for geom in aoi.geometry if geom is not None]

        if not geometries:
            raise ValueError("AOI has no valid geometry.")

        # Clip Red band
        red_clip, red_transform = mask(
            red_src,
            geometries,
            crop=True,
            filled=True,
            nodata=0
        )

        red_meta = red_src.meta.copy()

    # Open and clip NIR band
    with rasterio.open(nir_band_path) as nir_src:
        if nir_src.crs != raster_crs:
            raise ValueError("Red and NIR bands must have the same CRS.")

        nir_clip, nir_transform = mask(
            nir_src,
            geometries,
            crop=True,
            filled=True,
            nodata=0
        )

    # Convert to float
    red = red_clip[0].astype("float32")
    nir = nir_clip[0].astype("float32")

    # Treat zero pixels as NoData
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan

    # NDVI calculation
    denominator = nir + red

    ndvi = np.where(
        np.isnan(denominator) | (denominator == 0),
        np.nan,
        (nir - red) / denominator
    ).astype("float32")

    # Update metadata
    red_meta.update({
        "driver": "GTiff",
        "height": ndvi.shape[0],
        "width": ndvi.shape[1],
        "transform": red_transform,
        "count": 1,
        "dtype": "float32",
        "nodata": -9999
    })

    # Replace NaN with NoData value for saving
    ndvi_output = np.where(np.isnan(ndvi), -9999, ndvi).astype("float32")

    # Save output
    output_dir = os.path.dirname(output_ndvi_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with rasterio.open(output_ndvi_path, "w", **red_meta) as dst:
        dst.write(ndvi_output, 1)

    # Stats
    valid_ndvi = ndvi[~np.isnan(ndvi)]

    stats = {
        "output_path": output_ndvi_path,
        "valid_pixels": int(valid_ndvi.size),
    }

    if valid_ndvi.size > 0:
        stats.update({
            "min": float(np.nanmin(valid_ndvi)),
            "max": float(np.nanmax(valid_ndvi)),
            "mean": float(np.nanmean(valid_ndvi)),
        })
    else:
        stats["warning"] = "No valid NDVI pixels found. Check AOI overlap with raster."

    return stats




def calculate_ndvi(red_band_path, nir_band_path, aoi_path, output_ndvi_path):
    """
    Calculate NDVI from Landsat Red and NIR bands clipped to AOI.

    Landsat 8/9:
    Red = SR_B4
    NIR = SR_B5

    NDVI = (NIR - RED) / (NIR + RED)
    """

    # Check input files
    for path in [red_band_path, nir_band_path, aoi_path]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

    # Read AOI
    aoi = gpd.read_file(aoi_path)

    if aoi.empty:
        raise ValueError("AOI file is empty.")

    if aoi.crs is None:
        raise ValueError("AOI has no CRS. Make sure the .prj file exists for the shapefile.")

    # Open Red band
    with rasterio.open(red_band_path) as red_src:
        raster_crs = red_src.crs

        if raster_crs is None:
            raise ValueError("Red raster has no CRS.")

        # Reproject AOI to raster CRS
        if aoi.crs != raster_crs:
            aoi = aoi.to_crs(raster_crs)

        geometries = [geom for geom in aoi.geometry if geom is not None]

        if not geometries:
            raise ValueError("AOI has no valid geometry.")

        # Clip Red band
        red_clip, red_transform = mask(
            red_src,
            geometries,
            crop=True,
            filled=True,
            nodata=0
        )

        red_meta = red_src.meta.copy()

    # Open and clip NIR band
    with rasterio.open(nir_band_path) as nir_src:
        if nir_src.crs != raster_crs:
            raise ValueError("Red and NIR bands must have the same CRS.")

        nir_clip, nir_transform = mask(
            nir_src,
            geometries,
            crop=True,
            filled=True,
            nodata=0
        )

    # Convert to float
    red = red_clip[0].astype("float32")
    nir = nir_clip[0].astype("float32")

    # Treat zero pixels as NoData
    red[red == 0] = np.nan
    nir[nir == 0] = np.nan

    # NDVI calculation
    denominator = nir + red

    ndvi = np.where(
        np.isnan(denominator) | (denominator == 0),
        np.nan,
        (nir - red) / denominator
    ).astype("float32")

    # Update metadata
    red_meta.update({
        "driver": "GTiff",
        "height": ndvi.shape[0],
        "width": ndvi.shape[1],
        "transform": red_transform,
        "count": 1,
        "dtype": "float32",
        "nodata": -9999
    })

    # Replace NaN with NoData value for saving
    ndvi_output = np.where(np.isnan(ndvi), -9999, ndvi).astype("float32")

    # Save output
    output_dir = os.path.dirname(output_ndvi_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with rasterio.open(output_ndvi_path, "w", **red_meta) as dst:
        dst.write(ndvi_output, 1)

    # Stats
    valid_ndvi = ndvi[~np.isnan(ndvi)]

    stats = {
        "output_path": output_ndvi_path,
        "valid_pixels": int(valid_ndvi.size),
    }

    if valid_ndvi.size > 0:
        stats.update({
            "min": float(np.nanmin(valid_ndvi)),
            "max": float(np.nanmax(valid_ndvi)),
            "mean": float(np.nanmean(valid_ndvi)),
        })
    else:
        stats["warning"] = "No valid NDVI pixels found. Check AOI overlap with raster."

    return stats
