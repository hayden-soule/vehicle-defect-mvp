"""
app.py

Purpose:
- Streamlit UI for the Vehicle Defect Pattern Intelligence MVP.
- Provides a quick, attorney-friendly workflow:
    1) Select a vehicle via VIN or make/model/year
    2) Ingest/cached NHTSA complaints + recalls into SQLite
    3) Display case-strength indicators, defect patterns, trends, and text search results

Architecture notes:
- This UI is intentionally thin:
  * Ingestion lives in ingestion.py (external API → local DB)
  * Analytics queries live in queries.py (SQL aggregation)
  * ORM schema lives in database.py (SQLite persistence)
- The app reads from SQLite on each run to keep the UI responsive and deterministic.
"""

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
    get_recalls,
)

# Streamlit configuration:
# - "wide" layout gives more horizontal room for tables and charts.
st.set_page_config(page_title="SLP Defect Tool", layout="wide")

# Ensure DB tables exist before any UI or query work begins.
init_db()

st.title("SLP Vehicle Defect Pattern Intelligence Tool (MVP)")

# ----------------------------
# Sidebar: Vehicle selection + ingestion
# ----------------------------
with st.sidebar:
    st.header("Lookup")

    # Two user entry modes:
    # - VIN (common in intake calls)
    # - Make/model/year (manual entry or decoded VIN)
    lookup_mode = st.radio("Search by", ["VIN", "Make/Model/Year"])

    # Default values are set so the dashboard is immediately usable.
    # These variables are later used to query the local database.
    vin = ""
    make = "HONDA"
    model = "ACCORD"
    year = 2021

    if lookup_mode == "VIN":
        # VIN decoding is handled by ingestion.ingest_vin().
        vin = st.text_input("VIN (17 characters)")
    else:
        make = st.text_input("Make", value="HONDA")
        model = st.text_input("Model", value="ACCORD")
        year = st.number_input("Year", min_value=1990, max_value=2026, value=2021)

    # In Streamlit, button clicks are used to trigger stateful actions (API calls + DB writes).
    # This prevents re-ingestion on every rerun caused by UI interactions.
    if st.button("ENTER"):
        if lookup_mode == "VIN":
            # Import locally to keep VIN-specific logic optional and avoid unused imports.
            from ingestion import ingest_vin

            try:
                decoded, new_complaints, new_recalls = ingest_vin(vin)

                # After decoding, the dashboard uses make/model/year to query local data.
                # Updating these variables ensures downstream panels load the correct vehicle.
                make, model, year = decoded["make"], decoded["model"], decoded["year"]

                st.success(
                    f"VIN decoded → {year} {make} {model}. "
                )
            except Exception as e:
                # MVP UX: show a clean error message instead of a stack trace.
                st.error(str(e))
        else:
            # Ingest based on make/model/year using NHTSA complaints + recalls endpoints.
            new_complaints, new_recalls = ingest_vehicle(make, model, int(year))
            st.success(
                f"Vehicle selected."
            )

    st.divider()

    # Symptom search supports attorney workflow:
    # search narratives for terms like "stalling", "slipping", "loss of power", etc.
    st.header("Symptom Search")
    symptom = st.text_input("Search text", value="transmission")


# ----------------------------
# Main Page: Read analytics from SQLite and render dashboard
# ----------------------------
session = SessionLocal()
try:
    # The dashboard is driven by what exists in the local DB.
    # If the vehicle hasn't been ingested yet, the user is prompted to click ENTER.
    vehicle = get_vehicle(session, make, model, int(year))
    if not vehicle:
        st.warning("Click 'ENTER' in the sidebar to view vehicle statistics.")
        st.stop()

    # Prominent "context header" so the user always knows what vehicle they are viewing.
    st.markdown(f"## {vehicle.year} {vehicle.make} {vehicle.model}")

    # ----------------------------
    # High-level metrics (intake triage)
    # ----------------------------
    total = complaint_count(session, vehicle.id)
    sev = severity_summary(session, vehicle.id)

    # Key case-strength indicators displayed as quick metrics.
    # This mirrors how an intake team might assess case viability quickly.
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Complaints", total)
    c2.metric("Crashes", sev["crashes"])
    c3.metric("Fires", sev["fires"])
    c4.metric("Injuries", sev["injuries"])
    c5.metric("Deaths", sev["deaths"])

    # Recall count is displayed separately because recalls represent manufacturer/NHTSA acknowledgement.
    r_total = recall_count(session, vehicle.id)
    st.metric("Recalls", r_total)

    # ----------------------------
    # Recalls table (acknowledgement + remedy)
    # ----------------------------
    st.subheader("Recalls")
    recalls = get_recalls(session, vehicle.id)

    # Convert ORM objects into a dataframe-ready list for display.
    recall_rows = []
    for r in recalls:
        recall_rows.append(
            {
                "Campaign": r.campaign_number,
                "Report Date": r.report_received_date,
                "Component": r.component,
                "Summary": (r.summary or "")[:200],
                "Remedy": (r.remedy or "")[:200],
            }
        )

    if recall_rows:
        st.dataframe(pd.DataFrame(recall_rows), use_container_width=True)
    else:
        st.info("No recalls found for this vehicle.")

    # ----------------------------
    # Two-column layout: components + trend
    # ----------------------------
    left, right = st.columns(2)

    with left:
        st.subheader("Top Reported Complaints by Component")

        # MVP limitation:
        # - Components are stored as a comma-separated string rather than normalized components.
        # - This is still useful for quick pattern detection and triage.
        comp = top_components(session, vehicle.id, limit=12)
        st.dataframe(pd.DataFrame(comp), use_container_width=True)

    with right:
        st.subheader("Complaint Volume Over Time")

        # Trends help identify emerging patterns or spikes.
        trend = complaints_over_time(session, vehicle.id)
        dft = pd.DataFrame(trend)

        if not dft.empty:
            # Streamlit's built-in line_chart expects an index for the x-axis.
            dft = dft.set_index("month")
            st.line_chart(dft["count"])
        else:
            st.info("No dated complaints available for trend chart.")

    # ----------------------------
    # Text search results (symptom search)
    # ----------------------------
    st.subheader("Symptom Search Results")

    # If the user provided search text, run a case-insensitive substring match
    # on complaint summaries and component text.
    if symptom.strip():
        hits = search_by_symptom(session, vehicle.id, symptom.strip(), limit=50)

        hit_rows = []
        for h in hits:
            hit_rows.append(
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

        st.dataframe(pd.DataFrame(hit_rows), use_container_width=True)
    else:
        st.info("Enter a symptom/search phrase in the sidebar.")

finally:
    # Ensure the DB session is always closed even if Streamlit reruns or an exception occurs.
    session.close()