"""
Optional: populate the database with the same demo records used in the
original static prototype, so you can test the viewer immediately without
first uploading real shapefiles through the admin page.

Run once:
    python seed_data.py

Safe to re-run -- it skips records that already exist.
"""
import datetime
import json

from app.database import SessionLocal, engine, Base
from app.models import SpillRecord
from app.geo_utils import compute_area_km2

Base.metadata.create_all(bind=engine)

DEMO = [
    dict(id="OS-2020-001", name="Red Sea Northern Alpha Spill", region="Red Sea",
         spill_date="2020-03-22", severity="high", source="Tanker accident",
         vessel="MT Nour Al-Bahr", oil_type="Crude Oil", status="Dispersed",
         shapefile_name="RS_2020_03_Alpha.shp",
         geometry={"type": "Polygon", "coordinates": [[[34.85,28.45],[35.05,28.52],[35.18,28.40],[35.12,28.22],[34.95,28.15],[34.78,28.25],[34.75,28.38],[34.85,28.45]]]}),
    dict(id="OS-2020-002", name="Gulf of Suez Pipeline Rupture", region="Gulf of Suez",
         spill_date="2020-08-11", severity="critical", source="Pipeline rupture",
         vessel="N/A", oil_type="Heavy Fuel Oil", status="Contained",
         shapefile_name="GOSUEZ_2020_08_Pipeline.shp",
         geometry={"type": "Polygon", "coordinates": [[[32.60,29.90],[32.85,30.05],[33.00,29.85],[32.95,29.55],[32.72,29.45],[32.52,29.62],[32.50,29.78],[32.60,29.90]]]}),
    dict(id="OS-2021-001", name="Mediterranean Western Coast Spill", region="Mediterranean Sea",
         spill_date="2021-01-15", severity="medium", source="Vessel collision",
         vessel="MV Alexandros G", oil_type="Diesel", status="Resolved",
         shapefile_name="MED_2021_01_West.shp",
         geometry={"type": "Polygon", "coordinates": [[[29.45,31.40],[29.72,31.48],[29.88,31.32],[29.80,31.12],[29.58,31.05],[29.38,31.18],[29.35,31.32],[29.45,31.40]]]}),
    dict(id="OS-2021-002", name="Persian Gulf Offshore Platform Leak", region="Persian Gulf",
         spill_date="2021-04-03", severity="critical", source="Offshore platform",
         vessel="Platform Khaleej-7", oil_type="Crude Oil", status="Active",
         shapefile_name="PG_2021_04_Platform.shp",
         geometry={"type": "Polygon", "coordinates": [[[51.20,27.45],[51.55,27.62],[51.78,27.40],[51.68,27.10],[51.38,26.98],[51.12,27.15],[51.08,27.35],[51.20,27.45]]]}),
    dict(id="OS-2021-003", name="Nile Delta Coastal Seep", region="Nile Delta Coast",
         spill_date="2021-07-20", severity="low", source="Natural seep",
         vessel="N/A", oil_type="Natural Seepage", status="Monitoring",
         shapefile_name="NILE_DELTA_2021_07.shp",
         geometry={"type": "Polygon", "coordinates": [[[30.82,31.42],[30.95,31.48],[31.05,31.40],[31.02,31.30],[30.88,31.26],[30.75,31.33],[30.78,31.40],[30.82,31.42]]]}),
    dict(id="OS-2021-004", name="Gulf of Aden Tanker Grounding", region="Gulf of Aden",
         spill_date="2021-10-08", severity="high", source="Tanker accident",
         vessel="MT Sea Eagle", oil_type="Light Crude", status="Dispersed",
         shapefile_name="ADEN_2021_10.shp",
         geometry={"type": "Polygon", "coordinates": [[[46.15,12.55],[46.42,12.68],[46.58,12.48],[46.50,12.22],[46.22,12.12],[46.02,12.30],[46.00,12.48],[46.15,12.55]]]}),
    dict(id="OS-2022-001", name="Red Sea South Vessel Collision", region="Red Sea South",
         spill_date="2022-02-14", severity="medium", source="Vessel collision",
         vessel="MV Gulf Star", oil_type="Marine Diesel", status="Resolved",
         shapefile_name="RS_SOUTH_2022_02.shp",
         geometry={"type": "Polygon", "coordinates": [[[40.35,16.42],[40.58,16.52],[40.72,16.38],[40.65,16.18],[40.42,16.10],[40.22,16.25],[40.20,16.38],[40.35,16.42]]]}),
    dict(id="OS-2022-002", name="Arabian Sea Offshore Platform Release", region="Arabian Sea",
         spill_date="2022-05-30", severity="high", source="Offshore platform",
         vessel="Platform AR-19", oil_type="Crude Oil", status="Contained",
         shapefile_name="ARAB_SEA_2022_05.shp",
         geometry={"type": "Polygon", "coordinates": [[[58.85,20.25],[59.18,20.42],[59.38,20.22],[59.28,19.92],[58.95,19.78],[58.65,19.95],[58.62,20.15],[58.85,20.25]]]}),
    dict(id="OS-2022-003", name="Persian Gulf Pipeline Break", region="Persian Gulf",
         spill_date="2022-09-12", severity="critical", source="Pipeline rupture",
         vessel="N/A", oil_type="Heavy Crude", status="Resolved",
         shapefile_name="PG_2022_09_Pipeline.shp",
         geometry={"type": "Polygon", "coordinates": [[[50.10,26.82],[50.42,26.98],[50.62,26.78],[50.52,26.48],[50.22,26.35],[49.92,26.52],[49.90,26.72],[50.10,26.82]]]}),
    dict(id="OS-2022-004", name="Mediterranean Eastern Spill", region="Mediterranean Sea",
         spill_date="2022-11-05", severity="medium", source="Vessel collision",
         vessel="MT Poseidon IV", oil_type="Fuel Oil", status="Dispersed",
         shapefile_name="MED_2022_11_East.shp",
         geometry={"type": "Polygon", "coordinates": [[[32.55,32.15],[32.82,32.28],[32.98,32.10],[32.88,31.88],[32.62,31.78],[32.38,31.95],[32.38,32.08],[32.55,32.15]]]}),
    dict(id="OS-2023-001", name="Red Sea Cargo Ship Incident", region="Red Sea",
         spill_date="2023-03-17", severity="high", source="Tanker accident",
         vessel="MT Ocean Hawk", oil_type="Crude Oil", status="Active",
         shapefile_name="RS_2023_03_Cargo.shp",
         geometry={"type": "Polygon", "coordinates": [[[37.25,22.88],[37.52,23.02],[37.68,22.85],[37.58,22.60],[37.32,22.48],[37.08,22.65],[37.05,22.82],[37.25,22.88]]]}),
    dict(id="OS-2023-002", name="Gulf of Aden Eastern Leak", region="Gulf of Aden",
         spill_date="2023-06-22", severity="low", source="Vessel collision",
         vessel="MV Desert Wind", oil_type="Light Oil", status="Resolved",
         shapefile_name="ADEN_2023_06_East.shp",
         geometry={"type": "Polygon", "coordinates": [[[50.45,13.18],[50.65,13.28],[50.78,13.15],[50.72,12.98],[50.52,12.90],[50.32,13.02],[50.30,13.12],[50.45,13.18]]]}),
    dict(id="OS-2023-003", name="Gulf of Suez Natural Seep", region="Gulf of Suez",
         spill_date="2023-09-01", severity="low", source="Natural seep",
         vessel="N/A", oil_type="Natural Seepage", status="Monitoring",
         shapefile_name="GOSUEZ_2023_09_Seep.shp",
         geometry={"type": "Polygon", "coordinates": [[[33.25,27.85],[33.40,27.92],[33.50,27.82],[33.45,27.70],[33.30,27.64],[33.18,27.72],[33.18,27.82],[33.25,27.85]]]}),
    dict(id="OS-2024-001", name="Red Sea Cargo Vessel Fuel Leak", region="Red Sea South",
         spill_date="2024-01-08", severity="medium", source="Vessel collision",
         vessel="MV Horizon Star", oil_type="Bunker Fuel", status="Active",
         shapefile_name="RS_2024_01_Cargo.shp",
         geometry={"type": "Polygon", "coordinates": [[[39.45,19.75],[39.68,19.88],[39.82,19.72],[39.75,19.50],[39.52,19.40],[39.28,19.55],[39.25,19.70],[39.45,19.75]]]}),
    dict(id="OS-2024-002", name="Arabian Sea Deep Water Release", region="Arabian Sea",
         spill_date="2024-04-15", severity="critical", source="Offshore platform",
         vessel="Platform DW-42", oil_type="Crude Oil", status="Active",
         shapefile_name="ARAB_SEA_2024_04_Deep.shp",
         geometry={"type": "Polygon", "coordinates": [[[63.50,18.85],[63.95,19.12],[64.22,18.85],[64.08,18.42],[63.65,18.22],[63.22,18.48],[63.18,18.75],[63.50,18.85]]]}),
]


def run():
    db = SessionLocal()
    created = 0
    try:
        for d in DEMO:
            if db.query(SpillRecord).filter(SpillRecord.id == d["id"]).first():
                continue
            area = round(compute_area_km2(d["geometry"]), 2)
            rec = SpillRecord(
                id=d["id"], name=d["name"], region=d["region"],
                spill_date=datetime.date.fromisoformat(d["spill_date"]),
                severity=d["severity"], source=d["source"], vessel=d["vessel"],
                oil_type=d["oil_type"], status=d["status"], area_km2=area,
                geometry_geojson=json.dumps(d["geometry"]),
                shapefile_name=d["shapefile_name"], stored_zip_path=None,
            )
            db.add(rec)
            created += 1
        db.commit()
        print(f"Seeded {created} new record(s). {len(DEMO) - created} already existed.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
