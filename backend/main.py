# hello nada
# Hello Farohaa ❤️
from ast import Index
import os

# Point pyproj (used internally by geopandas) at rasterio's bundled PROJ
# database, which is the correct version. Must happen before any geopandas
# or pyproj import, otherwise PostgreSQL's PostGIS proj.db (wrong version)
# gets picked up from the system PATH.
import rasterio
os.environ["PROJ_DATA"] = os.path.join(os.path.dirname(rasterio.__file__), "proj_data")
os.environ["PROJ_LIB"]  = os.environ["PROJ_DATA"]

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
from public_transport import calculate_transit_coverage
from vegetation_density import calculate_vegetation_density
from grid_analysis import (
    grid_from_raster,
    grid_from_vector,
    grid_from_facility_accessibility,
    grid_from_transit_coverage,
    grid_from_vegetation,
)

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
        "X-Coverage-Pct", "X-Population-Pct", "X-Overall-Score",
        "X-Station-Count", "X-Walking-Distance-M",
        "X-Vegetation-Pct", "X-Benchmark-Gap", "X-Passes-Benchmark",
        "X-Valid-Pixels", "X-Vegetated-Pixels", "X-Cell-Size-M",
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


# ── Grid / Cell Analysis endpoints ───────────────────────────────────────────

@app.post("/calculate-grid/ndvi", tags=["Grid Analysis"])
def grid_ndvi_endpoint(
    geotiff: UploadFile = File(..., description="NDVI result GeoTIFF"),
):
    """Divide the NDVI raster into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "ndvi_result.tif"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        grid_geojson = grid_from_raster(str(input_path), "ndvi")
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid NDVI failed: {e}")


@app.post("/calculate-grid/heat-index", tags=["Grid Analysis"])
def grid_heat_index_endpoint(
    geotiff: UploadFile = File(..., description="Heat Index result GeoTIFF"),
):
    """Divide the Heat Index raster into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "heat_result.tif"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        grid_geojson = grid_from_raster(str(input_path), "heat-index")
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Heat Index failed: {e}")


@app.post("/calculate-grid/crime", tags=["Grid Analysis"])
def grid_crime_endpoint(
    geojson: UploadFile = File(..., description="Crime density result GeoJSON"),
):
    """Divide the crime density GeoJSON into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "crime_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_vector(str(input_path), "crime", "crime_density")
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Crime failed: {e}")


@app.post("/calculate-grid/urban-density", tags=["Grid Analysis"])
def grid_urban_density_endpoint(
    geojson: UploadFile = File(..., description="Urban density result GeoJSON"),
):
    """Divide the urban density GeoJSON into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "urban_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_vector(str(input_path), "urban-density", "urban_density")
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Urban Density failed: {e}")


@app.post("/calculate-transit-coverage", tags=["Public Transport"])
def calculate_transit_coverage_endpoint(
    stations_geojson: UploadFile = File(..., description="GeoJSON point layer of transit stations"),
    aoi_geojson: UploadFile = File(..., description="GeoJSON polygon of area of interest"),
    walking_distance_m: float = Query(1000.0, description="Walking buffer radius in metres (default 1000 m)"),
    population_geojson: UploadFile = File(None, description="Optional GeoJSON polygon layer with population data"),
    population_field: str = Query(None, description="Attribute name holding population counts (required if population_geojson provided)"),
):
    """
    Calculate public-transit walking coverage within an AOI using geometric buffers.

    Returns a GeoJSON FeatureCollection of covered and uncovered areas, with
    coverage statistics in response headers.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    transit_dir = get_output_subdir("public_transport")

    stations_path  = tmp_dir / "stations.geojson"
    aoi_path       = tmp_dir / "aoi.geojson"
    output_path    = transit_dir / f"transit_coverage_{job_id}.geojson"
    pop_path       = None

    try:
        with stations_path.open("wb") as f:
            shutil.copyfileobj(stations_geojson.file, f)
        with aoi_path.open("wb") as f:
            shutil.copyfileobj(aoi_geojson.file, f)

        if population_geojson is not None:
            pop_path = tmp_dir / "population.geojson"
            with pop_path.open("wb") as f:
                shutil.copyfileobj(population_geojson.file, f)

        result = calculate_transit_coverage(
            stations_geojson_path=str(stations_path),
            aoi_geojson_path=str(aoi_path),
            walking_distance_m=walking_distance_m,
            population_geojson_path=str(pop_path) if pop_path else None,
            population_field=population_field,
            output_path=str(output_path),
        )

        # Read the saved combined GeoJSON (covered + uncovered)
        with open(str(output_path), "r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        headers = {
            "X-Coverage-Pct":       str(result["coverage_pct"]),
            "X-Overall-Score":      str(result["overall_score"]),
            "X-Station-Count":      str(result["station_count"]),
            "X-Walking-Distance-M": str(result["walking_distance_m"]),
        }
        if result["population_pct"] is not None:
            headers["X-Population-Pct"] = str(result["population_pct"])

        return JSONResponse(content=geojson_data, headers=headers)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transit coverage calculation failed: {e}")


@app.post("/calculate-grid/public-transport", tags=["Grid Analysis"])
def grid_transit_coverage_endpoint(
    geojson: UploadFile = File(..., description="Transit coverage result GeoJSON (from /calculate-transit-coverage)"),
):
    """Divide the transit coverage GeoJSON into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "transit_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_transit_coverage(str(input_path))
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Public Transport failed: {e}")


@app.post("/calculate-vegetation-density", tags=["Vegetation Density"])
def calculate_vegetation_density_endpoint(
    geotiff: UploadFile = File(..., description="Multi-band GeoTIFF (Red+NIR auto-detected) or single-band NDVI raster"),
    ndvi_threshold: float = Query(0.2, description="NDVI threshold for vegetated classification (default 0.2)"),
):
    """
    Analyse vegetation density from a GeoTIFF raster (full extent).

    Red and NIR bands are detected automatically. Single-band files are
    treated as pre-computed NDVI. Returns a per-cell GeoJSON benchmarked
    against the 30% urban greenery standard.
    """
    job_id      = str(uuid.uuid4())
    tmp_dir     = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    veg_dir     = get_output_subdir("vegetation")

    tiff_path   = tmp_dir / "input.tif"
    output_path = veg_dir / f"vegetation_{job_id}.geojson"

    try:
        with tiff_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        result = calculate_vegetation_density(
            geotiff_path=str(tiff_path),
            ndvi_threshold=ndvi_threshold,
            output_path=str(output_path),
            tmp_dir=str(tmp_dir),
        )

        with open(str(output_path), "r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        return JSONResponse(
            content=geojson_data,
            headers={
                "X-Vegetation-Pct":    str(result["vegetation_pct"]),
                "X-Benchmark-Gap":     str(result["benchmark_gap"]),
                "X-Passes-Benchmark":  str(result["passes_benchmark"]).lower(),
                "X-Overall-Score":     str(result["overall_score"]),
                "X-Valid-Pixels":      str(result["valid_pixels"]),
                "X-Vegetated-Pixels":  str(result["vegetated_pixels"]),
                "X-Cell-Size-M":       str(result["cell_size_m"]),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vegetation density calculation failed: {e}")


@app.post("/calculate-grid/vegetation", tags=["Grid Analysis"])
def grid_vegetation_endpoint(
    geojson: UploadFile = File(..., description="Vegetation density result GeoJSON (from /calculate-vegetation-density)"),
):
    """Re-score the vegetation cell GeoJSON and return it for the grid/cell tab."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "veg_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_vegetation(str(input_path))
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Vegetation failed: {e}")


@app.post("/calculate-grid/facility-accessibility", tags=["Grid Analysis"])
def grid_facility_accessibility_endpoint(
    geojson: UploadFile = File(..., description="Facility accessibility result GeoJSON"),
):
    """Divide the facility accessibility GeoJSON into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "facility_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_facility_accessibility(str(input_path))
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Facility Accessibility failed: {e}")