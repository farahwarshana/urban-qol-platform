import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse

from ndvi import calculate_ndvi_from_bands

app = FastAPI(
    title="NDVI Calculator API",
    description="Upload a multi-band Landsat GeoTIFF. Bands 4 (Red) and 5 (NIR) are extracted and NDVI is returned.",
    version="2.0.0",
)

# ── Directories ───────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "temp_uploads"
OUTPUT_DIR = BASE_DIR / "outputs" / "ndvi"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "NDVI Calculator API is running."}


@app.post("/calculate-ndvi", tags=["NDVI"])
def calculate_ndvi_endpoint(
    geotiff: UploadFile = File(..., description="Multi-band Landsat GeoTIFF (must contain Band 4 Red and Band 5 NIR)"),
):
    """
    Upload a single multi-band Landsat GeoTIFF.
    The API extracts Band 4 (Red) and Band 5 (NIR), computes NDVI,
    and returns the result GeoTIFF directly — no polling needed.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    input_path  = tmp_dir / "input.tif"
    output_path = OUTPUT_DIR / f"ndvi_{job_id}.tif"

    try:
        # Save uploaded file to disk
        with input_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        # Run NDVI — blocks until complete, then responds
        stats = calculate_ndvi_from_bands(
            geotiff_path     = str(input_path),
            red_band_index   = 3,
            nir_band_index   = 4,
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
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
