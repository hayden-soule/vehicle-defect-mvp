"""
queries.py

Purpose:
- Contains all database read logic for the dashboard.
- Separates query/analytics logic from the Streamlit UI layer.
- Provides reusable functions for intake coordinators and attorneys to:
    * Count complaints
    * Assess severity indicators
    * Identify common failing components
    * Analyze complaint trends over time
    * Search by symptom text
    * Review recall activity

Design philosophy:
- Keep queries simple and readable (MVP clarity > micro-optimization).
- Use SQL aggregation where possible instead of Python loops.
"""

from sqlalchemy import func, case
from database import Vehicle, Complaint, Recall


def get_vehicle(session, make: str, model: str, year: int):
    """
    Retrieve a vehicle row by make/model/year.

    Make and model are stored uppercase in the database for consistency,
    so lookup normalizes inputs to uppercase as well.
    """
    return (
        session.query(Vehicle)
        .filter(
            Vehicle.make == make.upper(),
            Vehicle.model == model.upper(),
            Vehicle.year == year,
        )
        .one_or_none()
    )


def complaint_count(session, vehicle_id: int) -> int:
    """
    Return total number of complaints associated with a vehicle.
    Used for quick intake triage.
    """
    return (
        session.query(func.count(Complaint.id))
        .filter(Complaint.vehicle_id == vehicle_id)
        .scalar()
        or 0
    )


def severity_summary(session, vehicle_id: int):
    """
    Aggregate severity indicators across complaints.

    This summarizes:
        - number of complaints involving crashes
        - number involving fires
        - total injuries reported
        - total deaths reported
    """
    row = (
        session.query(
            # Count crash flags (True → 1, else 0)
            func.sum(case((Complaint.crash == True, 1), else_=0)).label("crashes"),

            # Count fire flags
            func.sum(case((Complaint.fire == True, 1), else_=0)).label("fires"),

            # Sum injuries (coalesce handles NULL → 0)
            func.sum(func.coalesce(Complaint.number_of_injuries, 0)).label("injuries"),

            # Sum deaths
            func.sum(func.coalesce(Complaint.number_of_deaths, 0)).label("deaths"),
        )
        .filter(Complaint.vehicle_id == vehicle_id)
        .one()
    )

    return {
        "crashes": int(row.crashes or 0),
        "fires": int(row.fires or 0),
        "injuries": int(row.injuries or 0),
        "deaths": int(row.deaths or 0),
    }


def top_components(session, vehicle_id: int, limit: int = 10):
    """
    Identify most frequently reported components.

    MVP limitation:
    - "components" is stored as a comma-separated string.
    - This groups by the entire string rather than splitting into normalized components.
    - A production system would normalize components into a separate table for cleaner analytics.
    """
    rows = (
        session.query(
            Complaint.components,
            func.count(Complaint.id).label("n")
        )
        .filter(Complaint.vehicle_id == vehicle_id)
        .group_by(Complaint.components)
        .order_by(func.count(Complaint.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {"components": r[0] or "(unknown)", "count": int(r[1])}
        for r in rows
    ]


def complaints_over_time(session, vehicle_id: int):
    """
    Aggregate complaint volume by month (YYYY-MM).

    This allows attorneys to:
        - Identify emerging defect patterns
        - Detect spikes after production changes
        - Spot early signals of systemic failures
    """
    rows = (
        session.query(
            # SQLite strftime used to bucket by year-month
            func.strftime("%Y-%m", Complaint.date_complaint_filed).label("ym"),
            func.count(Complaint.id).label("n"),
        )
        .filter(
            Complaint.vehicle_id == vehicle_id,
            Complaint.date_complaint_filed.isnot(None),
        )
        .group_by("ym")
        .order_by("ym")
        .all()
    )

    return [
        {"month": r[0], "count": int(r[1])}
        for r in rows
    ]


def search_by_symptom(session, vehicle_id: int, text: str, limit: int = 50):
    """
    Perform a simple case-insensitive search across:
        - Complaint summary text
        - Component field

    This supports attorney workflows like:
        "Find complaints mentioning 'transmission slipping'"

    MVP note:
    - Uses ILIKE (case-insensitive LIKE).
    - This is substring matching, not semantic search.
    - Could be extended with full-text search or embeddings later.
    """
    q = (
        session.query(Complaint)
        .filter(Complaint.vehicle_id == vehicle_id)
        .filter(
            Complaint.summary.ilike(f"%{text}%")
            | Complaint.components.ilike(f"%{text}%")
        )
        .order_by(Complaint.date_complaint_filed.desc().nullslast())
        .limit(limit)
        .all()
    )
    return q


def get_recalls(session, vehicle_id: int):
    """
    Retrieve all recalls associated with a vehicle,
    ordered by most recent first.

    Useful for determining:
        - Whether the manufacturer acknowledged a defect
        - Timeline alignment with complaint spikes
    """
    return (
        session.query(Recall)
        .filter(Recall.vehicle_id == vehicle_id)
        .order_by(Recall.report_received_date.desc().nullslast())
        .all()
    )


def recall_count(session, vehicle_id: int) -> int:
    """
    Return total number of recall campaigns for a vehicle.
    """
    return (
        session.query(func.count(Recall.id))
        .filter(Recall.vehicle_id == vehicle_id)
        .scalar()
        or 0
    )