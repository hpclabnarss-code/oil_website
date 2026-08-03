"""
Minimal backend for Oil Spill Viewer – serves static mock data.
No database, no shapefile parsing, no external dependencies.
All endpoints required by the frontend are implemented.
"""
import json
from datetime import date
from typing import Optional, List

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Oil Spill Viewer (Mock)")

# ─── Serve static frontend ─────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_viewer():
    return FileResponse("static/oil-spill-viewer.html")

@app.get("/admin")
async def serve_admin():
    return FileResponse("static/admin-upload.html")

# ─── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Mock data ─────────────────────────────────────────────
MOCK_SPILLS = [
    {
        "id": "OS-2023-001",
        "name": "Example Spill 1",
        "region": "North Sea",
        "spill_date": "2023-06-15",
        "severity": "high",
        "source": "Platform",
        "vessel": "N/A",
        "oil_type": "Crude",
        "status": "Active",
        "area_km2": 45.2,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [2.0, 58.0],
                    [2.5, 58.0],
                    [2.5, 58.5],
                    [2.0, 58.5],
                    [2.0, 58.0]
                ]
            ]
        },
        "shapefile_name": "example1.zip",
        "created_at": "2023-06-15T10:00:00"
    },
    {
        "id": "OS-2023-002",
        "name": "Example Spill 2",
        "region": "Gulf of Mexico",
        "spill_date": "2023-07-20",
        "severity": "critical",
        "source": "Ship",
        "vessel": "Tanker X",
        "oil_type": "Heavy",
        "status": "Monitoring",
        "area_km2": 120.8,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-95.0, 28.0],
                    [-94.5, 28.0],
                    [-94.5, 28.5],
                    [-95.0, 28.5],
                    [-95.0, 28.0]
                ]
            ]
        },
        "shapefile_name": "example2.zip",
        "created_at": "2023-07-20T14:30:00"
    },
    {
        "id": "OS-2023-003",
        "name": "Mediterranean Spill",
        "region": "Mediterranean",
        "spill_date": "2023-08-05",
        "severity": "medium",
        "source": "Pipeline",
        "vessel": "N/A",
        "oil_type": "Light",
        "status": "Contained",
        "area_km2": 8.5,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [12.0, 37.0],
                    [12.5, 37.0],
                    [12.5, 37.5],
                    [12.0, 37.5],
                    [12.0, 37.0]
                ]
            ]
        },
        "shapefile_name": "example3.zip",
        "created_at": "2023-08-05T09:15:00"
    }
]

# ─── Public endpoints ──────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/spills")
def list_spills(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    severity: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
):
    """
    Returns mock spills, optionally filtered by query parameters.
    """
    # Simple filter simulation (you can expand if needed)
    filtered = MOCK_SPILLS
    if date_from:
        filtered = [s for s in filtered if s["spill_date"] >= str(date_from)]
    if date_to:
        filtered = [s for s in filtered if s["spill_date"] <= str(date_to)]
    if severity:
        levels = [l.strip().lower() for l in severity.split(",") if l.strip()]
        filtered = [s for s in filtered if s["severity"].lower() in levels]
    if source:
        filtered = [s for s in filtered if s["source"] == source]
    if region:
        filtered = [s for s in filtered if s["region"] == region]
    return filtered

@app.get("/api/spills/{spill_id}")
def get_spill(spill_id: str):
    for s in MOCK_SPILLS:
        if s["id"] == spill_id:
            return s
    raise HTTPException(status_code=404, detail="Spill not found")

@app.get("/api/meta/sources")
def list_sources():
    # Return distinct sources from mock data
    sources = sorted({s["source"] for s in MOCK_SPILLS})
    return sources

@app.get("/api/meta/regions")
def list_regions():
    regions = sorted({s["region"] for s in MOCK_SPILLS})
    return regions

# ─── Admin endpoints (mock, minimal) ──────────────────────
@app.post("/api/admin/login")
def admin_login(payload: dict):
    # Simple hardcoded auth for testing
    if payload.get("username") == "admin" and payload.get("password") == "password":
        return {"token": "mock-jwt-token", "expires_in": 3600}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/admin/upload")
async def admin_upload():
    # Not implemented in mock version
    raise HTTPException(status_code=501, detail="Upload not available in mock backend")

@app.get("/api/admin/spills")
def admin_list_spills():
    # Return same as public list (no auth required in mock)
    return MOCK_SPILLS

@app.delete("/api/admin/spills/{spill_id}")
def admin_delete_spill(spill_id: str):
    raise HTTPException(status_code=501, detail="Delete not available in mock backend")

@app.get("/api/admin/spills/{spill_id}/download")
def admin_download_shapefile(spill_id: str):
    raise HTTPException(status_code=501, detail="Download not available in mock backend")

# ─────────────────────────────────────────────────────────────
# Optional: fallback for any other route (useful for debugging)
# ─────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "trace": traceback.format_exc()}
    )