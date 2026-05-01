# hello nada 

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from ndvi import calculate_ndvi_from_bands

app = FastAPI(
    title="NDVI Calculator API",
    description="Upload a multi-band Landsat GeoTIFF. Bands 4 (Red) and Band 5 (NIR) are extracted and NDVI is returned.",
    version="2.0.0",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Directories ───────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "temp_uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
def get_output_subdir(name):
    path = OUTPUT_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "NDVI Calculator API is running."}


@app.post("/calculate-ndvi", tags=["NDVI"])
def calculate_ndvi_endpoint(
    geotiff: UploadFile = File(..., description="Multi-band GeoTIFF (Landsat or Sentinel-2)"),
    satellite_type: str = Query("landsat", description="Satellite type: 'landsat' or 'sentinel2'"),
):
    """
    Upload a single multi-band GeoTIFF.
    The API extracts Red and NIR bands, computes NDVI,
    and returns the result GeoTIFF directly — no polling needed.
    """
    # Map satellite types to band indices (0-based)
    band_mapping = {
        "landsat": (3, 4),      # Band 4 Red, Band 5 NIR
        "sentinel2": (3, 7),     # Band 4 Red, Band 8 NIR
    }
    
    if satellite_type not in band_mapping:
        raise HTTPException(status_code=422, detail=f"Invalid satellite type: {satellite_type}. Use 'landsat' or 'sentinel2'.")
    
    red_band_index, nir_band_index = band_mapping[satellite_type]
    
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ndvi_dir = get_output_subdir("ndvi")

    input_path  = tmp_dir / "input.tif"    
    output_path = ndvi_dir / f"ndvi_{job_id}.tif"

    try:
        # Save uploaded file to disk
        with input_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        # Run NDVI — blocks until complete, then responds
        stats = calculate_ndvi_from_bands(
            geotiff_path     = str(input_path),
            red_band_index   = red_band_index,
            nir_band_index   = nir_band_index,
            output_ndvi_path = str(output_path),
        )

        # Return the NDVI GeoTIFF directly with stats in headers
        return FileResponse(
            path=str(output_path),
            media_type="image/tiff",
            filename=f"ndvi_{job_id}.tif",
            headers={
                "X-NDVI-Min":     str(stats.get("min", "")),
                "X-NDVI-Max":     str(stats.get("max", "")),
                "X-NDVI-Mean":    str(stats.get("mean", "")),
                "X-Valid-Pixels": str(stats.get("valid_pixels", "")),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NDVI calculation failed: {e}")