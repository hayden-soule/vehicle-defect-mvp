"""
ingestion.py

Purpose:
- Fetches vehicle defect data from official NHTSA public APIs and stores it locally in SQLite.
- This file is the "data pipeline" for the MVP: it normalizes external JSON into a relational schema.

Data sources used:
1) Complaints: NHTSA ODI consumer complaints API (complaintsByVehicle)
2) Recalls: NHTSA recall campaigns API (recallsByVehicle)
3) VIN decoding: NHTSA vPIC API (DecodeVinValues)

Key design choices:
- The pipeline is idempotent: running ingestion multiple times does not create duplicates.
  This is enforced by UNIQUE constraints in the database and handled via IntegrityError.
- JSON fields that can be lists/dicts (e.g., products) are stored as text for the MVP.
"""

import json
from datetime import datetime
import requests

from sqlalchemy.exc import IntegrityError
from database import SessionLocal, init_db, Vehicle, Complaint, Recall


def decode_vin(vin: str):
    """
    Decode a VIN via NHTSA vPIC.

    Returns:
      dict with keys: vin, make, model, year
      or None if decoding fails or VIN is not 17 characters.

    Why this exists:
    - Intake staff often has a VIN (not the exact canonical model name).
    - VIN decoding gives a best-effort make/model/year that can drive complaints/recalls lookups.
    """
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return None

    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}"
    params = {"format": "json"}

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("Results", [])
    if not results:
        return None

    # vPIC returns a list; typically the first item contains the decoded attributes.
    r = results[0]
    make = (r.get("Make") or "").strip()
    model = (r.get("Model") or "").strip()
    year = (r.get("ModelYear") or "").strip()

    # If required fields aren't present, treat this as a decode failure.
    if not (make and model and year.isdigit()):
        return None

    return {"vin": vin, "make": make, "model": model, "year": int(year)}


def ingest_vin(vin: str):
    """
    Convenience wrapper: VIN → (make, model, year) → ingest_vehicle.

    This keeps the ingestion logic centralized in ingest_vehicle() so the pipeline
    stays consistent regardless of whether input is VIN or a manual vehicle description.
    """
    decoded = decode_vin(vin)
    if not decoded:
        raise ValueError("Could not decode VIN (check VIN and try again).")

    # Reuse the existing ingestion pipeline (vehicle-based API endpoints)
    new_complaints, new_recalls = ingest_vehicle(
        decoded["make"], decoded["model"], decoded["year"]
    )
    return decoded, new_complaints, new_recalls


def _parse_date(s):
    """
    Parse common date formats seen in NHTSA API payloads into Python date objects.

    The API can return multiple date formats; for the MVP, unsupported formats are ignored.
    """
    if not s:
        return None

    # Seen formats: ISO date, US date, ISO datetime.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    # If the string doesn't match known formats, return None for MVP robustness.
    return None


def fetch_complaints_by_vehicle(make: str, model: str, year: int):
    """
    Fetch complaints for a given make/model/year from NHTSA's complaints API.

    Response shape (typical):
      {
        "count": <int>,
        "message": <str>,
        "results": [ { complaint_record }, ... ]
      }
    """
    url = "https://api.nhtsa.gov/complaints/complaintsByVehicle"
    params = {"make": make, "model": model, "modelYear": year}

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_recalls_by_vehicle(make: str, model: str, year: int):
    """
    Fetch recalls for a given make/model/year from NHTSA's recalls API.

    Note:
    - NHTSA’s model naming can be strict; certain decoded model strings may not be accepted.
      (This is a known limitation of an MVP approach that uses make/model/year rather than
      VIN-specific recall endpoints.)
    """
    url = "https://api.nhtsa.gov/recalls/recallsByVehicle"
    params = {"make": make, "model": model, "modelYear": year}

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_or_create_vehicle(session, make: str, model: str, year: int) -> Vehicle:
    """
    Returns a Vehicle row for (make, model, year), creating it if needed.

    Why:
    - Local caching is organized around a Vehicle dimension so multiple complaints/recalls
      can be aggregated and queried quickly.
    - Make/model are normalized to uppercase for consistent lookups.
    """
    v = (
        session.query(Vehicle)
        .filter(
            Vehicle.make == make.upper(),
            Vehicle.model == model.upper(),
            Vehicle.year == year,
        )
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
    """
    Insert complaint records into the database for a given vehicle.

    Deduplication:
    - Complaint.odi_number is UNIQUE. If the record already exists, insertion will raise
      IntegrityError and we roll back (no duplicate rows).

    MVP note:
    - "components" may be a list or scalar; it's stored as a comma-separated string.
    - "products" may be list/dict; it's stored as JSON text.
    """
    results = complaints_json.get("results", [])
    inserted = 0

    for r in results:
        # Known keys from the complaintsByVehicle endpoint:
        # ['odiNumber','manufacturer','crash','fire','numberOfInjuries','numberOfDeaths',
        #  'dateOfIncident','dateComplaintFiled','vin','components','summary','products']

        odi = str(r.get("odiNumber") or "").strip()
        if not odi:
            continue  # Skip malformed records without an ODI number.

        # Normalize components into a display-friendly string.
        components_val = r.get("components")
        if isinstance(components_val, list):
            components_str = ", ".join([str(x) for x in components_val if x is not None])
        else:
            components_str = str(components_val) if components_val is not None else None

        # Normalize products into stored text (JSON if structured).
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
            # If the ODI number already exists, ignore the duplicate and keep going.
            session.rollback()

    return inserted


def ingest_recalls(session, vehicle: Vehicle, recalls_json: dict) -> int:
    """
    Insert recall campaigns into the database for a given vehicle.

    Deduplication:
    - (vehicle_id, campaign_number) is UNIQUE. Duplicate campaigns are ignored.

    Field mapping note:
    - Recall payload keys can vary (different capitalization / naming conventions),
      so the mapping attempts multiple likely keys.
    """
    results = recalls_json.get("results", [])
    inserted = 0

    for r in results:
        # Field names vary; handle common variants safely.
        campaign = (
            r.get("NHTSACampaignNumber")
            or r.get("nhtsaCampaignNumber")
            or r.get("campaignNumber")
            or ""
        ).strip()
        if not campaign:
            continue

        rec = Recall(
            vehicle_id=vehicle.id,
            campaign_number=campaign,
            recall_number=r.get("RecallNumber") or r.get("ManufacturerRecallNumber"),
            report_received_date=_parse_date(r.get("ReportReceivedDate") or r.get("reportReceivedDate")),
            component=r.get("Component") or r.get("component"),
            summary=r.get("Summary") or r.get("summary"),

            # Note: NHTSA payload sometimes misspells "Consequence" as "Conequence".
            consequence=r.get("Conequence") or r.get("Consequence") or r.get("consequence"),
            remedy=r.get("Remedy") or r.get("remedy"),
            notes=r.get("Notes") or r.get("notes"),
        )

        session.add(rec)
        try:
            session.commit()
            inserted += 1
        except IntegrityError:
            # Duplicate campaign for this vehicle: ignore and continue.
            session.rollback()

    return inserted


def ingest_vehicle(make: str, model: str, year: int):
    """
    Main ingestion entry point for the MVP.

    Steps:
    1) Ensure tables exist (init_db)
    2) Find or create local Vehicle row for (make, model, year)
    3) Fetch complaints + insert (deduped)
    4) Fetch recalls + insert (deduped)

    Returns:
      (new_complaints_inserted, new_recalls_inserted)
    """
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
    # Basic local smoke test:
    # Running this file ingests one vehicle to verify API connectivity + DB writes.
    new_complaints, new_recalls = ingest_vehicle("HONDA", "ACCORD", 2021)
    print(f"Inserted {new_complaints} new complaints and {new_recalls} new recalls.")