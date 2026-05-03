# hello nada 
# Hello Farohaa ❤️
from ast import Index
import os
from pyproj import datadir

os.environ["PROJ_LIB"] = datadir.get_data_dir()

import shutil
import uuid
import geopandas as gpd
import json
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ndvi import calculate_ndvi_from_bands
from crimedensity import calculate_crime_density
from heat_index import calculate_heat_index_4326
from urbandensity import calculate_urban_density
from facility_Accessibility_index import calculate_facility_accessibility

app = FastAPI(
    title="Urban QOL API",
    description="Platform analyzes multiple aspects of urban quality of life in order to identify opportunities for enhancement.",
    version="1.0.0",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-NDVI-Min", "X-NDVI-Max", "X-NDVI-Mean", "X-Valid-Pixels",
        "X-Crime-Count", "X-Area-Count", "X-Avg-Density", "X-Max-Density",
        "X-Total-Population", "X-Total-Area",
        "X-HeatIndex-Min", "X-HeatIndex-Max", "X-HeatIndex-Mean",
    ],
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
    return {"status": "ok", "message": "Urban QOL API is running."}


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


@app.post("/calculate-crime-density", tags=["Crime Density"])
def calculate_crime_density_endpoint(
    csv: UploadFile = File(..., description="CSV file with crime incident locations"),
    geojson: UploadFile = File(..., description="GeoJSON file with boundary polygons"),
    lat_field: str = Query(..., description="Name of latitude field in CSV"),
    lon_field: str = Query(..., description="Name of longitude field in CSV"),
):
    """
    Upload CSV crime data and GeoJSON boundary polygons.
    The API calculates crime density per area unit and returns the result GeoJSON.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    crime_dir = get_output_subdir("crime")

    csv_path = tmp_dir / "input.csv"
    geojson_path = tmp_dir / "input.geojson"
    output_path = crime_dir / f"crime_density_{job_id}.geojson"

    try:
        # Save uploaded CSV file to disk
        with csv_path.open("wb") as f:
            shutil.copyfileobj(csv.file, f)

        # Save uploaded GeoJSON file to disk
        with geojson_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        print("Files saved, starting crime density calculation...")  # Debug log

        # Run crime density calculation
        result_gdf = calculate_crime_density(
            crime_csv=str(csv_path),
            area_shapefile=str(geojson_path),
            lat_field=lat_field,
            lon_field=lon_field,
            output_path=str(output_path),
        )

        # Calculate stats
        total_crimes = int(result_gdf['crime_count'].sum()) if 'crime_count' in result_gdf.columns else 0
        area_count = len(result_gdf)
        avg_density = float(result_gdf['crime_density'].mean()) if 'crime_density' in result_gdf.columns else 0
        max_density = float(result_gdf['crime_density'].max()) if 'crime_density' in result_gdf.columns else 0

        # Read the output GeoJSON and return as JSON
        with open(str(output_path), 'r') as f:
            import json
            geojson_data = json.load(f)

        # Return the crime density GeoJSON as JSON with stats in headers
        return JSONResponse(
            content=geojson_data,
            headers={
                "X-Crime-Count":   str(total_crimes),
                "X-Area-Count":    str(area_count),
                "X-Avg-Density":   str(round(avg_density, 2)),
                "X-Max-Density":   str(round(max_density, 2)),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Crime density calculation failed: {e}")


@app.post("/calculate-urban-density", tags=["Urban Density"])
def calculate_urban_density_endpoint(
    geojson: UploadFile = File(..., description="GeoJSON file with area polygons and population data"),
    population_field: str = Query(..., description="Name of population field in GeoJSON"),
):
    """
    Upload a GeoJSON file with area polygons and population data.
    The API calculates urban density (population per unit area) and returns the result GeoJSON.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    urban_dir = get_output_subdir("urban_density")

    geojson_path = tmp_dir / "input.geojson"
    output_path = urban_dir / f"urban_density_{job_id}.geojson"

    try:
        # Save uploaded GeoJSON file to disk
        with geojson_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        print("Files saved, starting urban density calculation...")  # Debug log

        # Run urban density calculation
        result_gdf = calculate_urban_density(
            population_geojson=str(geojson_path),
            population_field=population_field,
            output_path=str(output_path),
        )

        # Calculate stats
        total_population = int(result_gdf[population_field].sum()) if population_field in result_gdf.columns else 0
        total_area = float(result_gdf['area_km2'].sum()) if 'area_km2' in result_gdf.columns else 0
        area_count = len(result_gdf)
        avg_density = float(result_gdf['urban_density'].mean()) if 'urban_density' in result_gdf.columns else 0
        max_density = float(result_gdf['urban_density'].max()) if 'urban_density' in result_gdf.columns else 0

        # Read the output GeoJSON and return as JSON
        with open(str(output_path), 'r') as f:
            import json
            geojson_data = json.load(f)

        # Return the urban density GeoJSON as JSON with stats in headers
        return JSONResponse(
            content=geojson_data,
            headers={
                "X-Total-Population": str(total_population),
                "X-Total-Area":       str(round(total_area, 2)),
                "X-Area-Count":       str(area_count),
                "X-Avg-Density":      str(round(avg_density, 2)),
                "X-Max-Density":      str(round(max_density, 2)),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Urban density calculation failed: {e}")


@app.post("/calculate-heat-index", tags=["Heat Index"])
def calculate_heat_index_endpoint(
    lst_geotiff: UploadFile = File(..., description="LST GeoTIFF file")
):
    """
    Upload a single LST GeoTIFF.
    The API calculates Heat Index from the raster data
    and returns the result GeoTIFF directly — no polling needed.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    hi_dir = get_output_subdir("heat_index")

    input_path  = tmp_dir / "input.tif"
    output_path = hi_dir / f"heat_index_{job_id}.tif"

    try:
        # Save uploaded file to disk
        with input_path.open("wb") as f:
            shutil.copyfileobj(lst_geotiff.file, f)

        # Run Heat Index calculation (replace with your real logic)
        stats = calculate_heat_index_4326(
          str(input_path),
          str(output_path)
       )

        # Return the Heat Index GeoTIFF directly with stats in headers
        return FileResponse(
            path=str(output_path),
            media_type="image/tiff",
            filename=f"heat_index_{job_id}.tif",
            headers={
                "X-HeatIndex-Min":     str(stats.get("min_lst_c", "")),
                "X-HeatIndex-Max":     str(stats.get("max_lst_c", "")),
                "X-HeatIndex-Mean":    str(stats.get("mean_lst_c", "")),
                "X-Valid-Pixels":      str(stats.get("valid_pixels", "")),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Heat Index calculation failed: {e}")
    
    
# Facility Accessibility Index endpoint
    
@app.post("/calculate-facility-accessibility", tags=["Facility Accessibility"])
def calculate_facility_accessibility_endpoint(
    facilities_geojson: UploadFile = File(...),
    facility_id: int = Query(0)
):
    job_id = str(uuid.uuid4())

    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    facility_dir = get_output_subdir("facility_accessibility")
    input_path = tmp_dir / "facilities.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(facilities_geojson.file, f)

        stats = calculate_facility_accessibility(
            facilities_geojson_path=str(input_path),
            facility_id=facility_id,
            output_dir=str(facility_dir),
            walking_speed_kmh=4.5,
            times_minutes=[5, 10, 15],
            network_dist_m=2000
        )

        with open(stats["combined_output"], "r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        return JSONResponse(content=geojson_data)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Facility Accessibility failed: {e}"
        )