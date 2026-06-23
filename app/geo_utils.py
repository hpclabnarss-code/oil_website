"""
Geometry helpers: parsing an uploaded shapefile (.zip containing .shp/.shx/.dbf
and optionally .prj), reprojecting to WGS84 if needed, and computing an
approximate area in km^2 -- all using pure-Python / lightweight libraries
(pyshp + pyproj) so there's no GDAL/PostGIS system dependency required.
"""
import io
import os
import zipfile
import tempfile
import shutil
import datetime
from typing import Optional

import shapefile  # pyshp
from pyproj import CRS, Transformer, Geod

WGS84 = CRS.from_epsg(4326)
_GEOD = Geod(ellps="WGS84")


class ShapefileParseError(Exception):
    pass


def _find_member(names: list[str], ext: str) -> Optional[str]:
    ext = ext.lower()
    for n in names:
        if n.lower().endswith(ext):
            return n
    return None


def _parse_date_string(val: str) -> Optional[datetime.date]:
    """Try to parse a date from various common formats."""
    if not val:
        return None
    val = val.strip()
    # Try YYYY-MM-DD
    try:
        return datetime.datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        pass
    # Try MM/DD/YYYY
    try:
        return datetime.datetime.strptime(val, "%m/%d/%Y").date()
    except ValueError:
        pass
    # Try YYYYMMDD
    try:
        if len(val) == 8 and val.isdigit():
            return datetime.datetime.strptime(val, "%Y%m%d").date()
    except ValueError:
        pass
    return None


def _extract_date_from_attrs(attrs: dict) -> Optional[datetime.date]:
    """
    Look through the attribute dictionary for a field that looks like a date.
    Returns the first valid date found, or None.
    """
    # Common date column names (case-insensitive)
    date_keys = ['date', 'spill_date', 'spilldate', 'datetime', 'dt', 'time',
                 'event_date', 'eventdate', 'occurrence', 'occ_date']

    for key, value in attrs.items():
        # If value is already a date/datetime object (pyshp may return it)
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.date() if isinstance(value, datetime.datetime) else value

        # If it's a string, check key name and try parsing
        if isinstance(value, str):
            key_lower = key.lower()
            if any(dk in key_lower for dk in date_keys):
                parsed = _parse_date_string(value)
                if parsed:
                    return parsed
    return None


def _extract_area_from_attrs(attrs: dict) -> Optional[float]:
    """
    Look through the attribute dictionary for a field that looks like an area.
    Returns the first numeric area found, or None.
    """
    # Common area column names (case-insensitive)
    area_keys = ['area', 'area_km2', 'shape_area', 'shapearea', 'sqkm', 'km2', 'sq_km']

    for key, value in attrs.items():
        key_lower = key.lower()
        if any(ak in key_lower for ak in area_keys):
            # Try to convert to float
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
    return None


def parse_shapefile_zip(zip_bytes: bytes) -> dict:
    """
    Accepts the raw bytes of a .zip file containing a shapefile
    (.shp + .shx + .dbf, optionally .prj). Returns:

        {
            "geometry": <GeoJSON geometry dict, in WGS84 lon/lat>,
            "feature_count": int,
            "source_crs": str or None,
            "attributes": dict,          # first record's attributes
            "date": datetime.date or None,   # extracted date if found
            "area": float or None,       # extracted area if found
        }

    Multiple features in the shapefile are combined into a single
    GeometryCollection (or merged into a MultiPolygon if every shape is a
    polygon) so the whole upload maps to one spill record.
    """
    tmpdir = tempfile.mkdtemp(prefix="shp_upload_")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            shp_name = _find_member(names, ".shp")
            dbf_name = _find_member(names, ".dbf")
            shx_name = _find_member(names, ".shx")
            prj_name = _find_member(names, ".prj")

            if not shp_name or not dbf_name:
                raise ShapefileParseError(
                    "Zip file must contain at least a .shp and a .dbf component."
                )
            zf.extractall(tmpdir)

        shp_path = os.path.join(tmpdir, shp_name)
        reader = shapefile.Reader(shp_path)

        # Read shapes
        shapes = list(reader.shapes())
        if not shapes:
            raise ShapefileParseError("Shapefile contains no shapes.")

        geometries = [s.__geo_interface__ for s in shapes]

        # Read attributes (DBF records)
        records = list(reader.records())
        first_record = records[0] if records else None
        # Field names: skip the first (DeletionFlag)
        field_names = [f[0] for f in reader.fields[1:]]
        attributes = dict(zip(field_names, first_record)) if first_record else {}

        # Try to extract date and area from attributes
        extracted_date = _extract_date_from_attrs(attributes)
        extracted_area = _extract_area_from_attrs(attributes)

        # CRS handling
        source_crs = None
        if prj_name:
            prj_path = os.path.join(tmpdir, prj_name)
            with open(prj_path, "r") as f:
                wkt = f.read()
            try:
                source_crs = CRS.from_wkt(wkt)
            except Exception:
                source_crs = None

        if source_crs and not source_crs.equals(WGS84):
            geometries = [_reproject_geometry(g, source_crs) for g in geometries]
            source_crs_label = source_crs.name
        else:
            source_crs_label = "WGS84 (EPSG:4326)" if not source_crs else source_crs.name

        combined = _combine_geometries(geometries)

        return {
            "geometry": combined,
            "feature_count": len(geometries),
            "source_crs": source_crs_label,
            "attributes": attributes,
            "date": extracted_date,
            "area": extracted_area,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _reproject_coords(coords, transformer: Transformer):
    if isinstance(coords[0], (float, int)):
        x, y = coords[0], coords[1]
        lon, lat = transformer.transform(x, y)
        return [lon, lat]
    return [_reproject_coords(c, transformer) for c in coords]


def _reproject_geometry(geom: dict, source_crs: CRS) -> dict:
    transformer = Transformer.from_crs(source_crs, WGS84, always_xy=True)
    geom = dict(geom)
    geom["coordinates"] = _reproject_coords(geom["coordinates"], transformer)
    return geom


def _combine_geometries(geometries: list[dict]) -> dict:
    if len(geometries) == 1:
        return geometries[0]

    types = {g["type"] for g in geometries}
    if types <= {"Polygon"}:
        # Merge into a single MultiPolygon
        return {
            "type": "MultiPolygon",
            "coordinates": [g["coordinates"] for g in geometries],
        }
    return {"type": "GeometryCollection", "geometries": geometries}


def _ring_area_km2(ring: list) -> float:
    if len(ring) < 3:
        return 0.0
    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    area_m2, _ = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(area_m2) / 1_000_000.0


def compute_area_km2(geometry: dict) -> float:
    """Approximate geodesic area in km^2. Polygon holes are subtracted."""
    gtype = geometry.get("type")

    if gtype == "Polygon":
        rings = geometry["coordinates"]
        if not rings:
            return 0.0
        total = _ring_area_km2(rings[0])
        for hole in rings[1:]:
            total -= _ring_area_km2(hole)
        return max(total, 0.0)

    if gtype == "MultiPolygon":
        return sum(compute_area_km2({"type": "Polygon", "coordinates": poly}) for poly in geometry["coordinates"])

    if gtype == "GeometryCollection":
        return sum(compute_area_km2(g) for g in geometry.get("geometries", []))

    return 0.0