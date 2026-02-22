import pandas as pd
import streamlit as st

from database import SessionLocal, init_db
from ingestion import ingest_vehicle
from queries import (
    get_vehicle,
    complaint_count,
    severity_summary,
    top_components,
    complaints_over_time,
    search_by_symptom,
    recall_count,
    get_recalls
)

st.set_page_config(page_title="SLP Defect Tool", layout="wide")
init_db()

st.title("SLP Vehicle Defect Pattern Intelligence Tool (MVP)")

with st.sidebar:
    st.header("Lookup")

    lookup_mode = st.radio("Search by", ["VIN", "Make/Model/Year"])

    vin = ""
    make = "HONDA"
    model = "ACCORD"
    year = 2021

    if lookup_mode == "VIN":
        vin = st.text_input("VIN (17 characters)")
    else:
        make = st.text_input("Make", value="HONDA")
        model = st.text_input("Model", value="ACCORD")
        year = st.number_input("Year", min_value=1990, max_value=2026, value=2021)

    if st.button("ENTER"):
        if lookup_mode == "VIN":
            from ingestion import ingest_vin
            try:
                decoded, new_complaints, new_recalls = ingest_vin(vin)
                # Update downstream variables so the rest of the app loads correctly
                make, model, year = decoded["make"], decoded["model"], decoded["year"]
                st.success(
                    f"VIN decoded → {year} {make} {model}. "
                    f"Inserted {new_complaints} complaints and {new_recalls} recalls."
                )
            except Exception as e:
                st.error(str(e))
        else:
            new_complaints, new_recalls = ingest_vehicle(make, model, int(year))
            st.success(
                f"Ingestion complete. Inserted {new_complaints} complaints and {new_recalls} recalls."
            )

    st.divider()
    st.header("Symptom Search")
    symptom = st.text_input("Search text", value="transmission")

session = SessionLocal()
try:
    vehicle = get_vehicle(session, make, model, int(year))
    if not vehicle:
        st.warning("Vehicle not in database yet. Click 'Ingest / Refresh' in the sidebar.")
        st.stop()

    st.markdown(f"## {vehicle.year} {vehicle.make} {vehicle.model}")

    total = complaint_count(session, vehicle.id)
    sev = severity_summary(session, vehicle.id)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Complaints", total)
    c2.metric("Crashes", sev["crashes"])
    c3.metric("Fires", sev["fires"])
    c4.metric("Injuries", sev["injuries"])
    c5.metric("Deaths", sev["deaths"])

    
    r_total = recall_count(session, vehicle.id)
    st.metric("Recalls", r_total)

    st.subheader("Recalls")
    recalls = get_recalls(session, vehicle.id)

    rows = []
    for r in recalls:
        rows.append({
            "Campaign": r.campaign_number,
            "Report Date": r.report_received_date,
            "Component": r.component,
            "Summary": (r.summary or "")[:200],
            "Remedy": (r.remedy or "")[:200],
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No recalls found for this vehicle.")

    left, right = st.columns(2)

    with left:
        st.subheader("Top Reported Components (MVP grouping)")
        comp = top_components(session, vehicle.id, limit=12)
        dfc = pd.DataFrame(comp)
        st.dataframe(dfc, use_container_width=True)

    with right:
        st.subheader("Complaint Volume Over Time")
        trend = complaints_over_time(session, vehicle.id)
        dft = pd.DataFrame(trend)
        if not dft.empty:
            dft = dft.set_index("month")
            st.line_chart(dft["count"])
        else:
            st.info("No dated complaints available for trend chart.")

    st.subheader("Complaint Search Results")
    if symptom.strip():
        hits = search_by_symptom(session, vehicle.id, symptom.strip(), limit=50)
        rows = []
        for h in hits:
            rows.append(
                {
                    "ODI": h.odi_number,
                    "Filed": h.date_complaint_filed,
                    "Incident": h.date_of_incident,
                    "Crash": h.crash,
                    "Fire": h.fire,
                    "Injuries": h.number_of_injuries,
                    "Deaths": h.number_of_deaths,
                    "Components": h.components,
                    "Summary": (h.summary or "")[:200],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("Enter a symptom/search phrase in the sidebar.")
finally:
    session.close()