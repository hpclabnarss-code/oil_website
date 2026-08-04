"""
Oil Spill Viewer – Full Backend with Shapefile Upload Support
------------------------------------------------------------
- Uses SQLite for persistent storage
- Parses shapefiles from uploaded ZIP archives using pyshp + pyproj (app/geo_utils.py)
- Implements all CRUD endpoints
- Serves static frontend
"""

import json
import os
from datetime import date, datetime
from typing import Optional, List
from pathlib import Path
import uuid

from fastapi import FastAPI, Query, HTTPException, UploadFile, File, Form, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db, ensure_schema_updated
from app.models import SpillRecord
from app.geo_utils import parse_shapefile_zip, ShapefileParseError
from app.blob_storage import upload_zip, delete_zip, fetch_zip_bytes, BlobStorageError

# ============================================================================
# CONFIGURATION
# ============================================================================
STATIC_DIR = Path("static")

# Creates tables on the DB pointed to by DATABASE_URL (Postgres in prod,
# local sqlite fallback for dev — see app/database.py)
Base.metadata.create_all(bind=engine)

# ★ Auto‑migrate missing columns (fixes missing stored_zip_url, etc.)
ensure_schema_updated(engine)


def record_to_dict(record: SpillRecord) -> dict:
    return {
        "id": record.id,
        "name": record.name,
        "region": record.region,
        "spill_date": record.spill_date.isoformat() if record.spill_date else None,
        "severity": record.severity,
        "source": record.source,
        "vessel": record.vessel,
        "oil_type": record.oil_type,
        "status": record.status,
        "area_km2": record.area_km2,
        "geometry": json.loads(record.geometry_geojson) if record.geometry_geojson else None,
        "shapefile_name": record.shapefile_name,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


# ============================================================================
# FASTAPI APP
# ============================================================================
app = FastAPI(title="Oil Spill Viewer")

# ─── Serve static frontend ─────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_viewer():
    return FileResponse(str(STATIC_DIR / "oil-spill-viewer.html"))

@app.get("/admin")
async def serve_admin():
    return FileResponse(str(STATIC_DIR / "admin-upload.html"))

# ─── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# DEPENDENCIES
# ============================================================================
# get_db is imported from app.database above.


# Simple admin auth (hardcoded for dev – override with env vars)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")


def verify_token(token: str) -> bool:
    # In production, use proper JWT validation.
    # This mock simply checks a hardcoded token from login.
    return token == "mock-jwt-token" or token.startswith("mock-")


def get_token_from_header(authorization: Optional[str] = Header(None)) -> str:
    """Extract the bearer token from the Authorization header.

    The frontend sends `Authorization: Bearer <token>` — this replaces the
    old `token: str = Query(...)` param which the frontend never actually sent,
    causing every admin request to fail with a 422 validation error.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return authorization.removeprefix("Bearer ").strip()


def get_current_user(token: str = Depends(get_token_from_header)):
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"username": "admin"}


# ============================================================================
# SHAPEFILE PARSING HELPERS
# ============================================================================
def extract_shapefile_from_zip(zip_bytes: bytes) -> dict:
    """Extract shapefile data from ZIP bytes using the pure-Python parser
    (pyshp + pyproj, no GDAL/geopandas needed — see app/geo_utils.py)."""
    try:
        return parse_shapefile_zip(zip_bytes)
    except ShapefileParseError as e:
        raise HTTPException(400, str(e))


def guess_spill_metadata(parsed: dict) -> dict:
    """Attempt to auto-extract metadata from the shapefile's attributes."""
    meta = {
        "region": None,
        "severity": None,
        "source": None,
        "vessel": None,
        "oil_type": None,
        "status": None,
        "area_km2": parsed.get("area"),
        "spill_date": parsed["date"].strftime("%Y-%m-%d") if parsed.get("date") else None,
    }

    attrs = parsed.get("attributes") or {}
    for key, val in attrs.items():
        key_lower = key.lower()
        if val in (None, ""):
            continue
        if meta["region"] is None and any(h in key_lower for h in ["region", "location", "place"]):
            meta["region"] = str(val)
        if meta["severity"] is None and any(h in key_lower for h in ["sever", "impact", "magnitude"]):
            meta["severity"] = str(val).lower()

    return meta


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================
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
    db: Session = Depends(get_db),
):
    """Return all spills, optionally filtered."""
    query = db.query(SpillRecord)

    if date_from:
        query = query.filter(SpillRecord.spill_date >= date_from)
    if date_to:
        query = query.filter(SpillRecord.spill_date <= date_to)
    if severity:
        levels = [l.strip().lower() for l in severity.split(",") if l.strip()]
        query = query.filter(SpillRecord.severity.in_(levels))
    if source:
        query = query.filter(SpillRecord.source == source)
    if region:
        query = query.filter(SpillRecord.region == region)

    records = query.all()
    return [record_to_dict(r) for r in records]


@app.get("/api/spills/{spill_id}")
def get_spill(spill_id: str, db: Session = Depends(get_db)):
    record = db.query(SpillRecord).filter(SpillRecord.id == spill_id).first()
    if not record:
        raise HTTPException(404, "Spill not found")
    return record_to_dict(record)


@app.get("/api/meta/sources")
def list_sources(db: Session = Depends(get_db)):
    results = db.query(SpillRecord.source).distinct().all()
    return sorted([r[0] for r in results if r[0]])


@app.get("/api/meta/regions")
def list_regions(db: Session = Depends(get_db)):
    results = db.query(SpillRecord.region).distinct().all()
    return sorted([r[0] for r in results if r[0]])


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================
@app.post("/api/admin/login")
def admin_login(payload: dict):
    username = payload.get("username")
    password = payload.get("password")
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # In production, return a real JWT
        return {"token": "mock-jwt-token", "expires_in": 3600}
    raise HTTPException(401, "Invalid credentials")


@app.post("/api/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    spill_date: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    vessel: Optional[str] = Form(None),
    oil_type: Optional[str] = Form(None),
    status: Optional[str] = Form("Active"),
    token: str = Depends(get_token_from_header),
    db: Session = Depends(get_db),
):
    """Upload a shapefile ZIP archive and store its metadata."""
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")

    # Validate file type
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only .zip files are accepted")

    # Read ZIP contents
    zip_bytes = await file.read()
    if len(zip_bytes) == 0:
        raise HTTPException(400, "Empty file received")

    # Parse shapefile from ZIP
    try:
        parsed = extract_shapefile_from_zip(zip_bytes)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Failed to parse shapefile: {str(e)}")

    if not parsed.get("geometry"):
        raise HTTPException(400, "Shapefile contains no features")

    # Auto-detect metadata from shapefile
    auto_meta = guess_spill_metadata(parsed)

    # Use provided values, falling back to auto-detected
    final_name = name or file.filename.replace(".zip", "")
    final_date = spill_date or auto_meta.get("spill_date") or datetime.now().strftime("%Y-%m-%d")
    final_region = region or auto_meta.get("region") or "Unknown"
    final_vessel = vessel or auto_meta.get("vessel") or "N/A"
    final_oil_type = oil_type or auto_meta.get("oil_type") or "Unknown"
    final_status = status or auto_meta.get("status") or "Active"
    final_severity = auto_meta.get("severity") or "medium"
    final_area = auto_meta.get("area_km2") or 0.0

    # Geometry already comes back as GeoJSON (WGS84) from parse_shapefile_zip
    geojson_geom = parsed["geometry"]
    if not geojson_geom:
        raise HTTPException(400, "Shapefile has no valid geometry")

    # spill_date column is a real Date type — parse the "YYYY-MM-DD" string
    try:
        parsed_spill_date = datetime.strptime(final_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, f"Could not parse spill date: {final_date!r}")

    # Store the ZIP in Vercel Blob (local disk is read-only on Vercel)
    try:
        blob_url = upload_zip(file.filename, zip_bytes)
    except BlobStorageError as e:
        raise HTTPException(502, str(e))

    # Create database record
    record = SpillRecord(
        id=f"OS-{parsed_spill_date.year}-{uuid.uuid4().hex[:6].upper()}",
        name=final_name,
        region=final_region,
        spill_date=parsed_spill_date,
        severity=final_severity,
        source="Ship",  # Could be auto-detected
        vessel=final_vessel,
        oil_type=final_oil_type,
        status=final_status,
        area_km2=final_area,
        geometry_geojson=json.dumps(geojson_geom),
        shapefile_name=file.filename,
        stored_zip_url=blob_url,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "message": f"Uploaded {file.filename} successfully",
        "auto_detected": auto_meta,
        "record": record_to_dict(record),
    }


@app.get("/api/admin/spills")
def admin_list_spills(token: str = Depends(get_token_from_header), db: Session = Depends(get_db)):
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")
    records = db.query(SpillRecord).all()
    return [record_to_dict(r) for r in records]


@app.delete("/api/admin/spills/{spill_id}")
def admin_delete_spill(spill_id: str, token: str = Depends(get_token_from_header), db: Session = Depends(get_db)):
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")

    record = db.query(SpillRecord).filter(SpillRecord.id == spill_id).first()
    if not record:
        raise HTTPException(404, "Spill not found")

    # Delete the stored ZIP from Vercel Blob (never blocks record deletion)
    if record.stored_zip_url:
        delete_zip(record.stored_zip_url)

    db.delete(record)
    db.commit()
    return {"message": f"Deleted {spill_id}"}


@app.get("/api/admin/spills/{spill_id}/download")
def admin_download_shapefile(spill_id: str, token: str = Depends(get_token_from_header), db: Session = Depends(get_db)):
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")

    record = db.query(SpillRecord).filter(SpillRecord.id == spill_id).first()
    if not record:
        raise HTTPException(404, "Spill not found")
    if not record.stored_zip_url:
        raise HTTPException(404, "No shapefile stored for this record")

    try:
        zip_bytes = fetch_zip_bytes(record.stored_zip_url)
    except BlobStorageError as e:
        raise HTTPException(502, str(e))

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{record.name}.zip"'},
    )


# ============================================================================
# ERROR HANDLING
# ============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "trace": traceback.format_exc()}
    )


# ============================================================================
# RUN (for development)
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)