# NDVI Calculator — FastAPI Backend

## Setup

```bash
cd backend
pip install -r requirements.txt
```

## Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Interactive docs → http://localhost:8000/docs

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| POST | `/calculate-ndvi` | Upload bands + AOI, get NDVI stats |
| GET | `/download-ndvi/{job_id}` | Download the output GeoTIFF |

---

## POST `/calculate-ndvi` — required form fields

| Field | Type | Description |
|-------|------|-------------|
| `red_band` | GeoTIFF | Landsat Red band (SR_B4) |
| `nir_band` | GeoTIFF | Landsat NIR band (SR_B5) |
| `aoi_shp` | .shp | AOI shapefile |
| `aoi_prj` | .prj | Projection file |
| `aoi_dbf` | .dbf | Attribute file |
| `aoi_shx` | .shx | Index file |

### Example with curl

```bash
curl -X POST http://localhost:8000/calculate-ndvi \
  -F "red_band=@inputs/landsat/B4_red.tif" \
  -F "nir_band=@inputs/landsat/B5_nir.tif" \
  -F "aoi_shp=@inputs/aoi/AOI.shp" \
  -F "aoi_prj=@inputs/aoi/AOI.prj" \
  -F "aoi_dbf=@inputs/aoi/AOI.dbf" \
  -F "aoi_shx=@inputs/aoi/AOI.shx"
```

### Example response

```json
{
  "job_id": "a1b2c3d4-...",
  "output_file": "ndvi_a1b2c3d4-....tif",
  "download_url": "/download-ndvi/a1b2c3d4-...",
  "stats": {
    "output_path": "outputs/ndvi/ndvi_a1b2c3d4-....tif",
    "valid_pixels": 125430,
    "min": -0.12,
    "max": 0.87,
    "mean": 0.43
  }
}
```

## Folder structure

```
backend/
├── main.py             ← FastAPI app
├── ndvi.py             ← NDVI logic
├── requirements.txt
├── outputs/
│   └── ndvi/           ← Generated GeoTIFFs saved here
└── temp_uploads/       ← Auto-cleaned after each job
```
