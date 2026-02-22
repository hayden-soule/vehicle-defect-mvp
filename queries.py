from sqlalchemy import func, case
from database import Vehicle, Complaint, Recall


def get_vehicle(session, make: str, model: str, year: int):
    return (
        session.query(Vehicle)
        .filter(Vehicle.make == make.upper(), Vehicle.model == model.upper(), Vehicle.year == year)
        .one_or_none()
    )


def complaint_count(session, vehicle_id: int) -> int:
    return session.query(func.count(Complaint.id)).filter(Complaint.vehicle_id == vehicle_id).scalar() or 0


def severity_summary(session, vehicle_id: int):
    row = (
        session.query(
            func.sum(case((Complaint.crash == True, 1), else_=0)).label("crashes"),
            func.sum(case((Complaint.fire == True, 1), else_=0)).label("fires"),
            func.sum(func.coalesce(Complaint.number_of_injuries, 0)).label("injuries"),
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
    # components is stored as comma-separated; MVP approximation:
    # group by the whole string. Later you can normalize into a components table.
    rows = (
        session.query(Complaint.components, func.count(Complaint.id).label("n"))
        .filter(Complaint.vehicle_id == vehicle_id)
        .group_by(Complaint.components)
        .order_by(func.count(Complaint.id).desc())
        .limit(limit)
        .all()
    )
    return [{"components": r[0] or "(unknown)", "count": int(r[1])} for r in rows]


def complaints_over_time(session, vehicle_id: int):
    # group by month using date_complaint_filed
    rows = (
        session.query(
            func.strftime("%Y-%m", Complaint.date_complaint_filed).label("ym"),
            func.count(Complaint.id).label("n"),
        )
        .filter(Complaint.vehicle_id == vehicle_id, Complaint.date_complaint_filed.isnot(None))
        .group_by("ym")
        .order_by("ym")
        .all()
    )
    return [{"month": r[0], "count": int(r[1])} for r in rows]


def search_by_symptom(session, vehicle_id: int, text: str, limit: int = 50):
    q = (
        session.query(Complaint)
        .filter(Complaint.vehicle_id == vehicle_id)
        .filter(Complaint.summary.ilike(f"%{text}%") | Complaint.components.ilike(f"%{text}%"))
        .order_by(Complaint.date_complaint_filed.desc().nullslast())
        .limit(limit)
        .all()
    )
    return q

def get_recalls(session, vehicle_id: int):
    return (
        session.query(Recall)
        .filter(Recall.vehicle_id == vehicle_id)
        .order_by(Recall.report_received_date.desc().nullslast())
        .all()
    )

def recall_count(session, vehicle_id: int) -> int:
    return session.query(func.count(Recall.id)).filter(Recall.vehicle_id == vehicle_id).scalar() or 0