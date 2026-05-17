# hello nada
# Hello Farohaa ❤️
from ast import Index
import os
from pyproj import datadir

from dotenv import load_dotenv

load_dotenv()

proj_path = datadir.get_data_dir()

os.environ["PROJ_LIB"] = proj_path
os.environ["PROJ_DATA"] = proj_path

import shutil
import uuid
import geopandas as gpd
import json
from pathlib import Path

from sqlalchemy import create_engine, text

# DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/urban_qol"
# engine = create_engine(DATABASE_URL)

from database import engine
# __________________________auth import profile_1_______________

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

# -----------------------to render (url online)-----------------------------
from fastapi.staticfiles import StaticFiles
from fastapi import Request

# ------------------------------------------------------------------------------
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ndvi import calculate_ndvi_from_bands
from crimedensity import calculate_crime_density
from heat_index import calculate_heat_index_4326
from urbandensity import calculate_urban_density
from facility_Accessibility_index import calculate_facility_accessibility
from public_transport import calculate_transit_coverage
from vegetation_density import calculate_vegetation_density
from traffic_analysis import calculate_traffic_analysis
from informal_settlement import calculate_informal_settlement
from air_quality_index import calculate_air_quality_index
from grid_analysis import (
    grid_from_raster,
    grid_from_vector,
    grid_from_facility_accessibility,
    grid_from_transit_coverage,
    grid_from_vegetation,
    grid_from_traffic,
    grid_from_informal_settlement,
)

app = FastAPI(
    title="Urban QOL API",
    description="Platform analyzes multiple aspects of urban quality of life in order to identify opportunities for enhancement.",
    version="1.0.0",
)
# ----------------------api for (online url)-----------------------
BASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend"
)

app.mount("/css", StaticFiles(directory=os.path.join(BASE_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(BASE_DIR, "js")), name="js")
app.mount("/images", StaticFiles(directory=os.path.join(BASE_DIR, "images")), name="images")

# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Result-File",
        "X-NDVI-Min", "X-NDVI-Max", "X-NDVI-Mean", "X-Valid-Pixels", "X-NDVI-Stddev",
        "X-Red-Band", "X-NIR-Band", "X-Satellite",
        "X-Img-Width", "X-Img-Height", "X-Pixel-Size-X", "X-Pixel-Size-Y", "X-Pixel-Unit",
        "X-Pct-No-Veg", "X-Pct-Bare-Soil", "X-Pct-Moderate", "X-Pct-Dense",
        "X-Crime-Count", "X-Area-Count", "X-Avg-Density", "X-Max-Density",
        "X-Total-Population", "X-Total-Area",
        "X-HeatIndex-Min", "X-HeatIndex-Max", "X-HeatIndex-Mean",
        "X-Coverage-Pct", "X-Population-Pct", "X-Overall-Score",
        "X-Station-Count", "X-Walking-Distance-M",
        "X-Station-Distribution", "X-Avg-Station-Distance-M", "X-Gap-Regions",
        "X-Population-Density", "X-Demand-Pressure", "X-Pop-Adjusted-Insight",
        "X-Vegetation-Pct", "X-Benchmark-Gap", "X-Passes-Benchmark",
        "X-Valid-Pixels", "X-Vegetated-Pixels", "X-Cell-Size-M",
        "X-Road-Length-Km", "X-AOI-Area-Km2", "X-Road-Density",
        "X-Density-Class", "X-Traffic-Pressure", "X-High-Congestion-Pct",
        "X-Cell-Size-M",
        "X-Segment-Count", "X-Avg-Segment-Len-M", "X-Intersection-Density",
        "X-Connectivity-Index", "X-Primary-Pct", "X-Secondary-Pct", "X-Local-Pct",
        "X-Primary-Length-Km", "X-Secondary-Length-Km", "X-Local-Length-Km",
        "X-Fragmented-Zone-Pct",
        "X-Avg-Irregularity", "X-High-Pct", "X-Medium-Pct", "X-Low-Pct",
        "X-Overall-QoL-Score", "X-High-Zone-Count",
        "X-Pollutant", "X-Good-Pct", "X-Moderate-Pct", "X-Sensitive-Pct",
        "X-Unhealthy-Pct", "X-Very-Unhealthy-Pct", "X-Hazardous-Pct",
    ],
)

# ── Directories ───────────────────────────────────────────────────────────────
BACKEND_DIR   = Path(__file__).parent
UPLOAD_DIR = BACKEND_DIR / "temp_uploads"
OUTPUT_DIR = BACKEND_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
def get_output_subdir(name):
    path = OUTPUT_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path

app.mount(
    "/outputs",
    StaticFiles(directory=str(OUTPUT_DIR)),
    name="outputs"
)

def result_file_header(output_path):

    relative_path = Path(output_path)\
        .relative_to(BACKEND_DIR)

    return str(relative_path)\
        .replace("\\", "/")

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def Health():
    return {"status": "ok", "message": "Urban QOL API is running."}


@app.post("/calculate-ndvi", tags=["NDVI"])
def calculate_ndvi_endpoint(
    geotiff: UploadFile = File(..., description="Multi-band GeoTIFF (Landsat 8/9, Sentinel-2, or pre-extracted 2-band Red+NIR)"),
):
    """
    Upload a single multi-band GeoTIFF.
    The API auto-detects the satellite type, extracts Red and NIR bands, computes NDVI,
    and returns the result GeoTIFF directly — no polling needed.
    """
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

        # Run NDVI — bands detected automatically, blocks until complete, then responds
        stats = calculate_ndvi_from_bands(
            geotiff_path     = str(input_path),
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
                "X-Red-Band":       str(stats.get("red_band", "")),
                "X-NIR-Band":       str(stats.get("nir_band", "")),
                "X-Satellite":      str(stats.get("satellite", "")),
                "X-NDVI-Stddev":    str(stats.get("stddev", "")),
                "X-Img-Width":      str(stats.get("img_width", "")),
                "X-Img-Height":     str(stats.get("img_height", "")),
                "X-Pixel-Size-X":   str(stats.get("pixel_size_x", "")),
                "X-Pixel-Size-Y":   str(stats.get("pixel_size_y", "")),
                "X-Pixel-Unit":     str(stats.get("pixel_unit", "")),
                "X-Pct-No-Veg":     str(stats.get("pct_no_veg", "")),
                "X-Pct-Bare-Soil":  str(stats.get("pct_bare_soil", "")),
                "X-Pct-Moderate":   str(stats.get("pct_moderate", "")),
                "X-Pct-Dense":      str(stats.get("pct_dense", "")),
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
    lat_field: str = Query(None, description="Name of latitude field in CSV (auto-detected if omitted)"),
    lon_field: str = Query(None, description="Name of longitude field in CSV (auto-detected if omitted)"),
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
                "X-Result-File": f"outputs/urban_density/urban_density_{job_id}.geojson",
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
                "X-Result-File":
        result_file_header(output_path),
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
def facility_accessibility_endpoint(
    facilities_geojson: UploadFile = File(..., description="GeoJSON point layer of facilities"),
    walking_speed_kmh: float = Query(4.5, description="Walking speed in km/h (default 4.5)"),
    network_dist_m: int = Query(2000, description="OSM network download radius in metres (default 2000)"),
):
    """
    Compute 5, 10, and 15-minute walking isochrones for every point in the
    uploaded facilities GeoJSON.  Isochrones for each time band are unioned
    across all facilities and returned as a single FeatureCollection.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_dir / "facility_accessibility_zones.geojson"

    try:
        with (tmp_dir / "input.geojson").open("wb") as f:
            shutil.copyfileobj(facilities_geojson.file, f)

        result = calculate_facility_accessibility(
            facilities_geojson_path=str(tmp_dir / "input.geojson"),
            output_path=str(output_path),
            walking_speed_kmh=walking_speed_kmh,
            network_dist_m=network_dist_m,
        )

        with open(str(output_path), "r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        headers = {
            "X-Total-Facilities":     str(result["total_facilities"]),
            "X-Facilities-Processed": str(result["facilities_processed"]),
            "X-Walking-Speed-Kmh":    str(result["walking_speed_kmh"]),
            "X-Network-Dist-M":       str(result["network_dist_m"]),
        }
        if result["pct_5min"]  is not None: headers["X-Pct-5min"]  = str(result["pct_5min"])
        if result["pct_10min"] is not None: headers["X-Pct-10min"] = str(result["pct_10min"])
        if result["pct_15min"] is not None: headers["X-Pct-15min"] = str(result["pct_15min"])

        return JSONResponse(content=geojson_data, headers=headers)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Facility accessibility calculation failed: {e}")


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
    population_count: int = Query(None, description="Total population within the AOI as a plain integer (optional)"),
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
            population_count=population_count,
            output_path=str(output_path),
        )

        # Build combined GeoJSON (covered + uncovered + stations + aoi boundary)
        import copy
        combined_features = []

        with open(str(output_path), "r", encoding="utf-8") as f:
            coverage_geojson = json.load(f)
        combined_features.extend(coverage_geojson.get("features", []))

        # Add AOI boundary features
        for feat in result["aoi_geojson"].get("features", []):
            f2 = copy.deepcopy(feat)
            f2.setdefault("properties", {})["layer"] = "boundary"
            combined_features.append(f2)

        # Add station point features
        for feat in result["stations_geojson"].get("features", []):
            f2 = copy.deepcopy(feat)
            f2.setdefault("properties", {})["layer"] = "station"
            combined_features.append(f2)

        geojson_data = {"type": "FeatureCollection", "features": combined_features}

        import urllib.parse
        headers = {
            "X-Coverage-Pct":              str(result["coverage_pct"]),
            "X-Overall-Score":             str(result["overall_score"]),
            "X-Station-Count":             str(result["station_count"]),
            "X-Walking-Distance-M":        str(result["walking_distance_m"]),
            "X-Station-Distribution":      str(result["station_distribution"]),
            "X-Avg-Station-Distance-M":    str(result["avg_station_distance_m"] if result["avg_station_distance_m"] is not None else ""),
            "X-Gap-Regions":               urllib.parse.quote(json.dumps(result["gap_regions"])),
        }
        if result["population_pct"] is not None:
            headers["X-Population-Pct"] = str(result["population_pct"])
        if result.get("population_density") is not None:
            headers["X-Population-Density"]          = str(result["population_density"])
            headers["X-Demand-Pressure"]              = str(result["demand_pressure_indicator"])
            headers["X-Pop-Adjusted-Insight"]         = urllib.parse.quote(result["population_adjusted_insight"])

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


# ── Traffic / Road Analysis ───────────────────────────────────────────────────

@app.post("/calculate-traffic", tags=["Traffic Analysis"])
def calculate_traffic_endpoint(
    roads_geojson: UploadFile = File(..., description="GeoJSON LineString layer of road network"),
    aoi_geojson:   UploadFile = File(..., description="GeoJSON polygon of area of interest"),
    population:    float      = Query(None, description="Optional total population within the AOI"),
):
    """
    Analyse road network density and traffic congestion within an AOI.

    Returns a GeoJSON grid with per-cell congestion classification and
    a GeoJSON of merged high-congestion hotspot polygons. Summary stats
    are returned in response headers.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    traffic_dir = get_output_subdir("traffic")

    roads_path  = tmp_dir / "roads.geojson"
    aoi_path    = tmp_dir / "aoi.geojson"
    output_path = traffic_dir / f"traffic_{job_id}.geojson"

    try:
        with roads_path.open("wb") as f:
            shutil.copyfileobj(roads_geojson.file, f)
        with aoi_path.open("wb") as f:
            shutil.copyfileobj(aoi_geojson.file, f)

        result = calculate_traffic_analysis(
            roads_geojson_path=str(roads_path),
            aoi_geojson_path=str(aoi_path),
            population=population,
            output_path=str(output_path),
        )

        net = result["network"]

        # Combined response: network lines + grid cells + hotspot polygons
        # Each feature carries a "service" tag so the frontend can split them:
        #   "traffic-network" → full area tab (road hierarchy lines)
        #   "traffic"         → grid tab (congestion cells)
        #   type="hotspot"    → grid tab overlay
        combined = {
            "type": "FeatureCollection",
            "features": (
                net["network_geojson"]["features"] +
                result["grid_geojson"]["features"] +
                result["hotspots_geojson"]["features"]
            ),
            "cell_size_m":          result["cell_size_m"],
            "road_length_km":       result["road_length_km"],
            "aoi_area_km2":         result["aoi_area_km2"],
            "road_density":         result["road_density"],
            "density_class":        result["density_class"],
            "high_congestion_pct":  result["high_congestion_pct"],
        }

        headers = {
            "X-Road-Length-Km":        str(result["road_length_km"]),
            "X-AOI-Area-Km2":          str(result["aoi_area_km2"]),
            "X-Road-Density":          str(result["road_density"]),
            "X-Density-Class":         result["density_class"],
            "X-High-Congestion-Pct":   str(result["high_congestion_pct"]),
            "X-Cell-Size-M":           str(result["cell_size_m"]),
            # Network structural metrics
            "X-Segment-Count":         str(net["segment_count"]),
            "X-Avg-Segment-Len-M":     str(net["avg_segment_len_m"]),
            "X-Intersection-Density":  str(net["intersection_density"]),
            "X-Connectivity-Index":    str(net["connectivity_index"]),
            "X-Primary-Pct":           str(net["primary_pct"]),
            "X-Secondary-Pct":         str(net["secondary_pct"]),
            "X-Local-Pct":             str(net["local_pct"]),
            "X-Primary-Length-Km":     str(net["primary_length_km"]),
            "X-Secondary-Length-Km":   str(net["secondary_length_km"]),
            "X-Local-Length-Km":       str(net["local_length_km"]),
            "X-Fragmented-Zone-Pct":   str(net["fragmented_zone_pct"]),
        }
        if result["traffic_pressure"] is not None:
            headers["X-Traffic-Pressure"] = str(result["traffic_pressure"])

        return JSONResponse(content=combined, headers=headers)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Traffic analysis failed: {e}")


@app.post("/calculate-grid/traffic", tags=["Grid Analysis"])
def grid_traffic_endpoint(
    geojson: UploadFile = File(..., description="Traffic analysis result GeoJSON (from /calculate-traffic)"),
):
    """Re-score the traffic grid GeoJSON and return it for the grid/cell tab."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "traffic_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_traffic(str(input_path))
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Traffic failed: {e}")


# ── Informal Settlement Pattern Analysis ─────────────────────────────────────

@app.post("/calculate-informal-settlement", tags=["Informal Settlement"])
def calculate_informal_settlement_endpoint(
    geotiff: UploadFile = File(..., description="Satellite or aerial imagery GeoTIFF"),
):
    """
    Analyse informal settlement patterns from a GeoTIFF raster.

    Uses texture irregularity, edge density, and built-up crowding to score
    each cell 0–100 (0 = planned/formal, 100 = irregular/informal) and
    classify as Low / Medium / High. High-irregularity cells are merged into
    zone polygons. Returns a combined GeoJSON with statistics in headers.
    """
    job_id      = str(uuid.uuid4())
    tmp_dir     = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ispa_dir    = get_output_subdir("informal_settlement")

    tiff_path   = tmp_dir / "input.tif"
    output_path = ispa_dir / f"informal_settlement_{job_id}.geojson"

    try:
        with tiff_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        result = calculate_informal_settlement(
            geotiff_path=str(tiff_path),
            output_path=str(output_path),
            tmp_dir=str(tmp_dir),
        )

        with open(str(output_path), "r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        return JSONResponse(
            content=geojson_data,
            headers={
                "X-Avg-Irregularity":  str(result["avg_irregularity"]),
                "X-High-Pct":          str(result["high_pct"]),
                "X-Medium-Pct":        str(result["medium_pct"]),
                "X-Low-Pct":           str(result["low_pct"]),
                "X-Overall-QoL-Score": str(result["overall_qol_score"]),
                "X-Cell-Size-M":       str(result["cell_size_m"]),
                "X-High-Zone-Count":   str(result["high_zone_count"]),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Informal settlement analysis failed: {e}")


@app.post("/calculate-grid/informal-settlement", tags=["Grid Analysis"])
def grid_informal_settlement_endpoint(
    geojson: UploadFile = File(..., description="Informal settlement result GeoJSON (from /calculate-informal-settlement)"),
):
    """Re-score the informal settlement grid GeoJSON and return it for the grid/cell tab."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "ispa_result.geojson"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geojson.file, f)

        grid_geojson = grid_from_informal_settlement(str(input_path))
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Informal Settlement failed: {e}")


# ── Air Quality Index ─────────────────────────────────────────────────────────

@app.post("/calculate-air-quality", tags=["Air Quality Index"])
def calculate_air_quality_endpoint(
    geotiff: UploadFile = File(..., description="Pollutant or AQI GeoTIFF (PM2.5, PM10, NO2, or direct AQI)"),
):
    """
    Upload a single-band GeoTIFF containing PM2.5, PM10, NO2, or pre-computed AQI values.
    The API classifies pixels into 6 AQI categories (0 = Good … 5 = Hazardous),
    reprojects to EPSG:4326, and returns the result GeoTIFF with stats in headers.
    Pollutant type is auto-detected from the filename.
    """
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    aqi_dir = get_output_subdir("air_quality")

    input_path  = tmp_dir / geotiff.filename
    output_path = aqi_dir / f"air_quality_{job_id}.tif"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        stats = calculate_air_quality_index(str(input_path), str(output_path))

        return FileResponse(
            path=str(output_path),
            media_type="image/tiff",
            filename=f"air_quality_{job_id}.tif",
            headers={
                "X-Pollutant":          stats["pollutant"],
                "X-Valid-Pixels":       str(stats["valid_pixels"]),
                "X-Good-Pct":           str(stats["good_pct"]),
                "X-Moderate-Pct":       str(stats["moderate_pct"]),
                "X-Sensitive-Pct":      str(stats["sensitive_pct"]),
                "X-Unhealthy-Pct":      str(stats["unhealthy_pct"]),
                "X-Very-Unhealthy-Pct": str(stats["very_unhealthy_pct"]),
                "X-Hazardous-Pct":      str(stats["hazardous_pct"]),
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Air quality calculation failed: {e}")


@app.post("/calculate-grid/air-quality", tags=["Grid Analysis"])
def grid_air_quality_endpoint(
    geotiff: UploadFile = File(..., description="Air quality result GeoTIFF (from /calculate-air-quality)"),
):
    """Divide the AQI raster into adaptive-size cells and score each cell for QoL."""
    job_id  = str(uuid.uuid4())
    tmp_dir = UPLOAD_DIR / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_path = tmp_dir / "aqi_result.tif"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(geotiff.file, f)

        grid_geojson = grid_from_raster(str(input_path), "air-quality")
        return JSONResponse(content=grid_geojson)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid Air Quality failed: {e}")
    
#---------------------- endpoint profile_1 -------------------

from pydantic import BaseModel
from typing import Optional, List

class UserProfile(BaseModel):
    full_name: str
    email: str
    city: Optional[str] = ""
    organization: Optional[str] = ""
    phone: Optional[str] = ""


def init_db():
    with engine.connect() as conn:

        # Users table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                full_name VARCHAR(200),
                email VARCHAR(200),
                city VARCHAR(100),
                organization VARCHAR(200),
                initials VARCHAR(5),
                password VARCHAR(255),
                phone VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Analyses table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                type VARCHAR(100),
                title VARCHAR(200),
                area VARCHAR(200),
                score INTEGER,
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.commit()


init_db()


@app.get("/profile", tags=["User"])
def get_profile(username: str = "default"):

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE username = :username"),
            {"username": username}
        ).fetchone()

        if not result:
            return {
                "full_name": "",
                "email": "",
                "city": "",
                "organization": "",
                "initials": "",
                "phone": ""
            }

        return {
            "full_name": result.full_name,
            "email": result.email,
            "city": result.city,
            "organization": result.organization,
            "initials": result.initials,
            "phone": result.phone
        }


@app.post("/profile", tags=["User"])
def save_profile(profile: UserProfile, username: str = "default"):

    names = profile.full_name.strip().split()

    initials = (
        (names[0][0] + names[-1][0]).upper()
        if len(names) >= 2
        else names[0][0].upper()
    )

    with engine.begin() as conn:

        conn.execute(text("""
            INSERT INTO users (
                username,
                full_name,
                email,
                city,
                organization,
                initials,
                phone
            )
            VALUES (
                :username,
                :full_name,
                :email,
                :city,
                :organization,
                :initials,
                :phone
            )

            ON CONFLICT (username)
            DO UPDATE SET
                full_name = EXCLUDED.full_name,
                email = EXCLUDED.email,
                city = EXCLUDED.city,
                organization = EXCLUDED.organization,
                initials = EXCLUDED.initials,
                phone = EXCLUDED.phone
        """), {
            "username": username,
            "full_name": profile.full_name,
            "email": profile.email,
            "city": profile.city,
            "organization": profile.organization,
            "initials": initials,
            "phone": profile.phone
        })

    return {"message": "Profile saved successfully"}

# ------------------------ Authentication  endpoints-----------------
import bcrypt
from datetime import datetime, timedelta

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password[:72].encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password[:72].encode(), hashed.encode())


class UserRegister(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = ""

class UserLogin(BaseModel):
    email: str
    password: str

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/register", tags=["Auth"])
def register(user: UserRegister):
    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": user.email}
        ).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = hash_password(user.password)
    names = user.full_name.strip().split() if user.full_name else [user.username]
    initials = (names[0][0] + names[-1][0]).upper() if len(names) >= 2 else names[0][0].upper()
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (username, email, full_name, initials, password)
            VALUES (:username, :email, :full_name, :initials, :password)
        """), {
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "initials": initials,
            "password": hashed_password
        })
    
    token = create_token({"sub": user.email})
    return {"token": token, "username": user.username}

@app.post("/login", tags=["Auth"])
def login(user: UserLogin):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE email = :email"),
            {"email": user.email}
        ).fetchone()
    
    if not result:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(user.password, result.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_token({"sub": user.email})
    return {"token": token, "username": result.username}

# ____________AnalysisRecord_________

class AnalysisRecord(BaseModel):

    type: str
    title: str
    area: str
    score: int
    status: str

    preview_image: str | None = None

    result_file: str | None = None

@app.post("/analyses", tags=["User"])
def save_analysis(analysis: AnalysisRecord, username: str):

    with engine.begin() as conn:

        conn.execute(text("""
            INSERT INTO analyses (
                username,
                type,
                title,
                area,
                score,
                status,
                preview_image,
                result_file
            )
            VALUES (
                :username,
                :type,
                :title,
                :area,
                :score,
                :status,
                :preview_image,
                :result_file
            )
        """), {
            "username": username,
            "type": analysis.type,
            "title": analysis.title,
            "area": analysis.area,
            "score": analysis.score,
            "status": analysis.status,
            "preview_image": analysis.preview_image,
            "result_file": analysis.result_file
        })

    return {"message": "Analysis saved successfully"}


@app.get("/analyses", tags=["User"])
def get_analyses(username: str):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM analyses WHERE username = :username ORDER BY created_at DESC"),
            {"username": username}
        ).fetchall()

        return [
            {
                "id": row.id,
                "type": row.type,
                "title": row.title,
                "area": row.area,
                "score": row.score,
                "status": row.status,
                "created_at": str(row.created_at),
                "preview_image": row.preview_image,
                "result_file": row.result_file
            }
            for row in result
        ]
    # -------------------- endpoint (online url)-----------------
@app.get("/", tags=["Frontend"])
def root():
    return FileResponse(
        os.path.join(BASE_DIR, "index3.html")
    )

@app.get("/{page_name}.html", tags=["Frontend"])
def serve_html_page(page_name: str):
    file_path = os.path.join(BASE_DIR, page_name + ".html")

    if os.path.isfile(file_path):
        return FileResponse(file_path)

    return {"error": "HTML page not found", "path": file_path}