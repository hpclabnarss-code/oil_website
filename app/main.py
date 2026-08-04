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
import shutil
import tempfile
import zipfile
from datetime import date, datetime
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sqlalchemy as sa
from sqlalchemy import create_engine, Column, String, Float, DateTime, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.geo_utils import parse_shapefile_zip, ShapefileParseError
import uuid

# ============================================================================
# CONFIGURATION
# ============================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./oil_spill.db")
STATIC_DIR = Path("static")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ============================================================================
# DATABASE SETUP
# ============================================================================
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SpillRecord(Base):
    __tablename__ = "spills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    region = Column(String(100))
    spill_date = Column(String(20), nullable=False)
    severity = Column(String(20))          # high / medium / low / critical
    source = Column(String(50))            # Platform / Ship / Pipeline
    vessel = Column(String(100))
    oil_type = Column(String(50))
    status = Column(String(50), default="Active")
    area_km2 = Column(Float)
    geometry_json = Column(Text)           # GeoJSON geometry string
    shapefile_name = Column(String(200))   # stored ZIP filename on disk
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "spill_date": self.spill_date,
            "severity": self.severity,
            "source": self.source,
            "vessel": self.vessel,
            "oil_type": self.oil_type,
            "status": self.status,
            "area_km2": self.area_km2,
            "geometry": json.loads(self.geometry_json) if self.geometry_json else None,
            "shapefile_name": self.shapefile_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


Base.metadata.create_all(bind=engine)

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
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Simple admin auth (hardcoded for dev – override with env vars)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")


def verify_token(token: str) -> bool:
    # In production, use proper JWT validation.
    # This mock simply checks a hardcoded token from login.
    return token == "mock-jwt-token" or token.startswith("mock-")


def get_current_user(token: str = Query(...)):
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
        query = query.filter(SpillRecord.spill_date >= str(date_from))
    if date_to:
        query = query.filter(SpillRecord.spill_date <= str(date_to))
    if severity:
        levels = [l.strip().lower() for l in severity.split(",") if l.strip()]
        query = query.filter(SpillRecord.severity.in_(levels))
    if source:
        query = query.filter(SpillRecord.source == source)
    if region:
        query = query.filter(SpillRecord.region == region)

    records = query.all()
    return [r.to_dict() for r in records]


@app.get("/api/spills/{spill_id}")
def get_spill(spill_id: str, db: Session = Depends(get_db)):
    record = db.query(SpillRecord).filter(SpillRecord.id == spill_id).first()
    if not record:
        raise HTTPException(404, "Spill not found")
    return record.to_dict()


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
    token: str = Query(...),
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

    # Store the ZIP file on disk
    stored_filename = f"{uuid.uuid4()}_{file.filename}"
    stored_path = UPLOAD_DIR / stored_filename
    with open(stored_path, "wb") as f:
        f.write(zip_bytes)

    # Create database record
    record = SpillRecord(
        name=final_name,
        region=final_region,
        spill_date=final_date,
        severity=final_severity,
        source="Ship",  # Could be auto-detected
        vessel=final_vessel,
        oil_type=final_oil_type,
        status=final_status,
        area_km2=final_area,
        geometry_json=json.dumps(geojson_geom),
        shapefile_name=stored_filename,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "message": f"Uploaded {file.filename} successfully",
        "auto_detected": auto_meta,
        "record": record.to_dict(),
    }


@app.get("/api/admin/spills")
def admin_list_spills(token: str = Query(...), db: Session = Depends(get_db)):
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")
    records = db.query(SpillRecord).all()
    return [r.to_dict() for r in records]


@app.delete("/api/admin/spills/{spill_id}")
def admin_delete_spill(spill_id: str, token: str = Query(...), db: Session = Depends(get_db)):
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")

    record = db.query(SpillRecord).filter(SpillRecord.id == spill_id).first()
    if not record:
        raise HTTPException(404, "Spill not found")

    # Delete the stored ZIP file
    if record.shapefile_name:
        zip_path = UPLOAD_DIR / record.shapefile_name
        if zip_path.exists():
            zip_path.unlink()

    db.delete(record)
    db.commit()
    return {"message": f"Deleted {spill_id}"}


@app.get("/api/admin/spills/{spill_id}/download")
def admin_download_shapefile(spill_id: str, token: str = Query(...), db: Session = Depends(get_db)):
    if not verify_token(token):
        raise HTTPException(401, "Invalid or expired token")

    record = db.query(SpillRecord).filter(SpillRecord.id == spill_id).first()
    if not record:
        raise HTTPException(404, "Spill not found")
    if not record.shapefile_name:
        raise HTTPException(404, "No shapefile stored for this record")

    zip_path = UPLOAD_DIR / record.shapefile_name
    if not zip_path.exists():
        raise HTTPException(404, "Shapefile file missing on disk")

    return FileResponse(
        path=str(zip_path),
        filename=f"{record.name}.zip",
        media_type="application/zip",
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