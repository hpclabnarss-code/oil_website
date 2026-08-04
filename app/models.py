from sqlalchemy import Column, String, Date, Float, Text, LargeBinary, DateTime
from sqlalchemy.sql import func
from app.database import Base

class SpillRecord(Base):
    __tablename__ = "spill_records"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    region = Column(String, nullable=True)
    spill_date = Column(Date, nullable=True)
    severity = Column(String, nullable=True)
    source = Column(String, nullable=True)
    vessel = Column(String, nullable=True)
    oil_type = Column(String, nullable=True)
    status = Column(String, nullable=True)
    area_km2 = Column(Float, nullable=True)
    geometry_geojson = Column(Text, nullable=True)
    shapefile_name = Column(String, nullable=True)
    stored_zip_url = Column(String, nullable=True)   # kept but not used
    zip_data = Column(LargeBinary, nullable=True)    # NEW
    created_at = Column(DateTime, server_default=func.now())