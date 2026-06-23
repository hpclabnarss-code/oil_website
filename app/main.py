"""
Oil Spill Shapefile Backend
============================

Run locally:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Public endpoints (used by the map viewer page):
    GET  /api/spills?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&severity=high,critical&source=...
    GET  /api/spills/{id}
    GET  /api/meta/sources
    GET  /api/meta/regions

Admin endpoints (used by the admin upload page):
    POST   /api/admin/login                       {username, password} -> {token}
    POST   /api/admin/upload   [Bearer token]      multipart: file=<shapefile .zip> + metadata fields
    GET    /api/admin/spills   [Bearer token]      full record list incl. shapefile/admin-only fields
    DELETE /api/admin/spills/{id} [Bearer token]
    GET    /api/admin/spills/{id}/download [Bearer token]   -> original uploaded .zip

See README.md for the metadata fields the upload form must send.
"""
import datetime
import json
import os
import uuid
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_

from . import models, schemas, security, geo_utils
from .database import engine, Base, get_db, BASE_DIR

# Create the app first
app = FastAPI(title="Oil Spill Shapefile API", version="1.0.0")

# Then the startup event
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

# Use environment variable for upload dir
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# SERVE STATIC FRONTEND FILES
# ─────────────────────────────────────────────────────────────
# Place your HTML files inside a folder named "static" at the project root.
# - static/oil-spill-viewer.html  -> served at /
# - static/admin-upload.html      -> served at /admin
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_viewer():
    return FileResponse("static/oil-spill-viewer.html")

@app.get("/admin")
async def serve_admin():
    return FileResponse("static/admin-upload.html")

# ─────────────────────────────────────────────────────────────
# CORS (development only – restrict origins in production)
# ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _record_to_out(rec: models.SpillRecord) -> dict:
    return {
        "id": rec.id,
        "name": rec.name,
        "region": rec.region,
        "spill_date": rec.spill_date,
        "severity": rec.severity,
        "source": rec.source,
        "vessel": rec.vessel,
        "oil_type": rec.oil_type,
        "status": rec.status,
        "area_km2": rec.area_km2,
        "geometry": json.loads(rec.geometry_geojson),
        "shapefile_name": rec.shapefile_name,
        "created_at": rec.created_at,
    }


# ─────────────────────────────────────────────────────────────
# PUBLIC ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/spills", response_model=List[schemas.SpillOut])
def list_spills(
    date_from: Optional[datetime.date] = Query(None),
    date_to: Optional[datetime.date] = Query(None),
    severity: Optional[str] = Query(None, description="Comma-separated: critical,high,medium,low"),
    source: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(models.SpillRecord)

    if date_from:
        q = q.filter(models.SpillRecord.spill_date >= date_from)
    if date_to:
        q = q.filter(models.SpillRecord.spill_date <= date_to)
    if severity:
        levels = [s.strip().lower() for s in severity.split(",") if s.strip()]
        if levels:
            q = q.filter(models.SpillRecord.severity.in_(levels))
    if source:
        q = q.filter(models.SpillRecord.source == source)
    if region:
        q = q.filter(models.SpillRecord.region == region)

    records = q.order_by(models.SpillRecord.spill_date.desc()).all()
    return [_record_to_out(r) for r in records]


@app.get("/api/spills/{spill_id}", response_model=schemas.SpillOut)
def get_spill(spill_id: str, db: Session = Depends(get_db)):
    rec = db.query(models.SpillRecord).filter(models.SpillRecord.id == spill_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Spill record not found")
    return _record_to_out(rec)


@app.get("/api/meta/sources")
def list_sources(db: Session = Depends(get_db)):
    rows = db.query(models.SpillRecord.source).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


@app.get("/api/meta/regions")
def list_regions(db: Session = Depends(get_db)):
    rows = db.query(models.SpillRecord.region).distinct().all()
    return sorted({r[0] for r in rows if r[0]})


# ─────────────────────────────────────────────────────────────
# ADMIN: AUTH
# ─────────────────────────────────────────────────────────────

@app.post("/api/admin/login", response_model=schemas.LoginResponse)
def admin_login(payload: schemas.LoginRequest):
    if not security.check_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = security.issue_token()
    return {"token": token, "expires_in": security.TOKEN_TTL_SECONDS}


# ─────────────────────────────────────────────────────────────
# ADMIN: UPLOAD / MANAGE SHAPEFILES
# ─────────────────────────────────────────────────────────────

@app.post("/api/admin/upload", response_model=schemas.SpillOut)
async def upload_shapefile(
    file: UploadFile = File(..., description="A .zip containing .shp/.shx/.dbf (+ optional .prj)"),
    name: Optional[str] = Form(None),
    spill_date: Optional[datetime.date] = Form(None),
    severity: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    vessel: Optional[str] = Form(None),
    oil_type: Optional[str] = Form(None),
    status: Optional[str] = Form("Active"),
    spill_id: Optional[str] = Form(None, description="Optional custom ID, auto-generated if omitted"),
    db: Session = Depends(get_db),
    _admin=Depends(security.require_admin),
):
    # --- Validate file ---
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file containing the shapefile components.")

    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # --- Parse shapefile ---
    try:
        parsed = geo_utils.parse_shapefile_zip(raw)
    except geo_utils.ShapefileParseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse shapefile: {e}")

    geometry = parsed["geometry"]

    # --- AREA: MUST be present in shapefile attributes ---
    area_km2 = parsed.get("area")
    if area_km2 is None:
        raise HTTPException(
            status_code=400,
            detail="No area found in shapefile attributes. "
                   "Please ensure the shapefile has an area column (e.g., 'Area', 'Shape_Area', 'area_km2')."
        )
    # Convert to float and round
    try:
        area_km2 = round(float(area_km2), 2)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Area value '{area_km2}' could not be interpreted as a number."
        )

    # --- Auto-fill name if not provided ---
    if not name:
        name = file.filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()

    # --- DATE: REQUIRE either manual input OR extracted from shapefile ---
    extracted_date = parsed.get("date")
    if not spill_date and not extracted_date:
        raise HTTPException(
            status_code=400,
            detail="No date found in shapefile attributes and no date provided. "
                   "Please either provide a date manually or ensure the shapefile "
                   "has a date column (e.g., 'date', 'spill_date')."
        )
    if not spill_date:
        spill_date = extracted_date

    # --- Auto-fill severity if not provided ---
    if not severity:
        severity = "medium"

    # --- Generate ID ---
    rid = spill_id.strip() if spill_id else f"OS-{spill_date.year}-{uuid.uuid4().hex[:6].upper()}"
    if db.query(models.SpillRecord).filter(models.SpillRecord.id == rid).first():
        raise HTTPException(status_code=409, detail=f"A record with id '{rid}' already exists.")

    # --- Persist the original zip on disk ---
    stored_name = f"{rid}_{uuid.uuid4().hex[:8]}.zip"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    with open(stored_path, "wb") as f:
        f.write(raw)

    # --- Create database record ---
    rec = models.SpillRecord(
        id=rid,
        name=name,
        region=region,
        spill_date=spill_date,
        severity=severity.lower(),
        source=source,
        vessel=vessel,
        oil_type=oil_type,
        status=status,
        area_km2=area_km2,
        geometry_geojson=json.dumps(geometry),
        shapefile_name=file.filename,
        stored_zip_path=stored_path,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return _record_to_out(rec)


@app.get("/api/admin/spills", response_model=List[schemas.SpillOut])
def admin_list_spills(db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    records = db.query(models.SpillRecord).order_by(models.SpillRecord.created_at.desc()).all()
    return [_record_to_out(r) for r in records]


@app.delete("/api/admin/spills/{spill_id}", response_model=schemas.MessageResponse)
def admin_delete_spill(spill_id: str, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    rec = db.query(models.SpillRecord).filter(models.SpillRecord.id == spill_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Spill record not found")
    if rec.stored_zip_path and os.path.exists(rec.stored_zip_path):
        os.remove(rec.stored_zip_path)
    db.delete(rec)
    db.commit()
    return {"message": f"Deleted {spill_id}"}


@app.get("/api/admin/spills/{spill_id}/download")
def admin_download_shapefile(spill_id: str, db: Session = Depends(get_db), _admin=Depends(security.require_admin)):
    rec = db.query(models.SpillRecord).filter(models.SpillRecord.id == spill_id).first()
    if not rec or not rec.stored_zip_path or not os.path.exists(rec.stored_zip_path):
        raise HTTPException(status_code=404, detail="Original shapefile not found on server")
    return FileResponse(rec.stored_zip_path, filename=rec.shapefile_name or f"{spill_id}.zip")