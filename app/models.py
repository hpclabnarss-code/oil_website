"""
ORM model for a single oil spill shapefile record.

Geometry is stored as a GeoJSON string. This keeps the schema database-
agnostic (works on plain SQLite as well as Postgres) and lets the frontend
consume it directly with Leaflet's L.geoJSON(), with no translation layer.
"""
import datetime
from sqlalchemy import Column, String, Float, Date, DateTime, Text
from .database import Base


class SpillRecord(Base):
    __tablename__ = "spill_records"

    id = Column(String, primary_key=True, index=True)          # e.g. "OS-2024-001"
    name = Column(String, nullable=False)
    region = Column(String, nullable=True, index=True)          # kept for admin's own records
    spill_date = Column(Date, nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)        # critical / high / medium / low
    source = Column(String, nullable=True)
    vessel = Column(String, nullable=True)
    oil_type = Column(String, nullable=True)
    status = Column(String, nullable=True)
    area_km2 = Column(Float, nullable=True)

    geometry_geojson = Column(Text, nullable=False)              # GeoJSON geometry as text
    shapefile_name = Column(String, nullable=True)               # original uploaded filename
    stored_zip_path = Column(String, nullable=True)              # path to saved original zip on disk

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
