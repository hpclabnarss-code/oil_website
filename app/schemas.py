import datetime
from typing import Optional, Any
from pydantic import BaseModel


class SpillOut(BaseModel):
    id: str
    name: str
    region: Optional[str] = None
    spill_date: datetime.date
    severity: str
    source: Optional[str] = None
    vessel: Optional[str] = None
    oil_type: Optional[str] = None
    status: Optional[str] = None
    area_km2: Optional[float] = None
    geometry: Any                       # parsed GeoJSON geometry dict
    shapefile_name: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int


class MessageResponse(BaseModel):
    message: str
