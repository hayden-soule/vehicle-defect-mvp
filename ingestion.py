import json
from datetime import datetime
import requests

from sqlalchemy.exc import IntegrityError
from database import SessionLocal, init_db, Vehicle, Complaint, Recall


def _parse_date(s):
    """Parse common NHTSA date strings to date objects."""
    if not s:
        return None
    # Seen formats: "2021-05-14", "05/14/2021", sometimes timestamps.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # If it's something else, just skip for MVP
    return None


def fetch_complaints_by_vehicle(make: str, model: str, year: int):
    url = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
    params = {"make": make, "model": model, "modelYear": year}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_recalls_by_vehicle(make: str, model: str, year: int):
    url = "https://api.nhtsa.gov/recalls/recallsByVehicle"
    params = {"make": make, "model": model, "modelYear": year}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_or_create_vehicle(session, make: str, model: str, year: int) -> Vehicle:
    v = (
        session.query(Vehicle)
        .filter(Vehicle.make == make.upper(), Vehicle.model == model.upper(), Vehicle.year == year)
        .one_or_none()
    )
    if v:
        return v

    v = Vehicle(make=make.upper(), model=model.upper(), year=year)
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def ingest_complaints(session, vehicle: Vehicle, complaints_json: dict) -> int:
    results = complaints_json.get("results", [])
    inserted = 0

    for r in results:
        # Your keys list:
        # ['odiNumber','manufacturer','crash','fire','numberOfInjuries','numberOfDeaths',
        #  'dateOfIncident','dateComplaintFiled','vin','components','summary','products']
        odi = str(r.get("odiNumber") or "").strip()
        if not odi:
            continue

        components_val = r.get("components")
        if isinstance(components_val, list):
            components_str = ", ".join([str(x) for x in components_val if x is not None])
        else:
            components_str = str(components_val) if components_val is not None else None

        products_val = r.get("products")
        if isinstance(products_val, (list, dict)):
            products_str = json.dumps(products_val)
        else:
            products_str = str(products_val) if products_val is not None else None

        c = Complaint(
            vehicle_id=vehicle.id,
            odi_number=odi,
            manufacturer=r.get("manufacturer"),
            crash=bool(r.get("crash")) if r.get("crash") is not None else None,
            fire=bool(r.get("fire")) if r.get("fire") is not None else None,
            number_of_injuries=int(r.get("numberOfInjuries")) if r.get("numberOfInjuries") is not None else None,
            number_of_deaths=int(r.get("numberOfDeaths")) if r.get("numberOfDeaths") is not None else None,
            date_of_incident=_parse_date(r.get("dateOfIncident")),
            date_complaint_filed=_parse_date(r.get("dateComplaintFiled")),
            vin=r.get("vin"),
            components=components_str,
            summary=r.get("summary"),
            products=products_str,
        )

        session.add(c)
        try:
            session.commit()
            inserted += 1
        except IntegrityError:
            # duplicate odi_number; ignore
            session.rollback()

    return inserted

def ingest_recalls(session, vehicle: Vehicle, recalls_json: dict) -> int:
    results = recalls_json.get("results", [])
    inserted = 0

    for r in results:
        # Field names vary a bit; handle common ones safely.
        campaign = (r.get("NHTSACampaignNumber") or r.get("nhtsaCampaignNumber") or r.get("campaignNumber") or "").strip()
        if not campaign:
            continue

        rec = Recall(
            vehicle_id=vehicle.id,
            campaign_number=campaign,
            recall_number=r.get("RecallNumber") or r.get("ManufacturerRecallNumber"),
            report_received_date=_parse_date(r.get("ReportReceivedDate") or r.get("reportReceivedDate")),
            component=r.get("Component") or r.get("component"),
            summary=r.get("Summary") or r.get("summary"),
            consequence=r.get("Conequence") or r.get("Consequence") or r.get("consequence"),
            remedy=r.get("Remedy") or r.get("remedy"),
            notes=r.get("Notes") or r.get("notes"),
        )

        session.add(rec)
        try:
            session.commit()
            inserted += 1
        except IntegrityError:
            session.rollback()

    return inserted

def ingest_vehicle(make: str, model: str, year: int):
    init_db()
    session = SessionLocal()
    try:
        vehicle = get_or_create_vehicle(session, make, model, year)

        complaints_json = fetch_complaints_by_vehicle(make, model, year)
        new_complaints = ingest_complaints(session, vehicle, complaints_json)

        recalls_json = fetch_recalls_by_vehicle(make, model, year)
        new_recalls = ingest_recalls(session, vehicle, recalls_json)

        return new_complaints, new_recalls
    finally:
        session.close()


if __name__ == "__main__":
    inserted = ingest_vehicle("HONDA", "ACCORD", 2021)
    print(f"Inserted {inserted} new complaints.")