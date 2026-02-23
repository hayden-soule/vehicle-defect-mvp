# SLP Vehicle Defect Pattern Intelligence Tool (MVP)

## Overview

This project is a working prototype of a vehicle defect intelligence dashboard designed to support intake coordinators and attorneys evaluating potential automotive defect cases.

Given a VIN or make/model/year, the system:

* Retrieves consumer complaints from NHTSA’s ODI database
* Retrieves official recall campaigns from NHTSA
* Highlights severity indicators (crashes, fires, injuries, deaths)
* Identifies defect patterns by component
* Displays complaint volume trends over time
* Enables symptom-based complaint search

All data is sourced from official NHTSA public APIs and cached locally in SQLite for analysis.

---

## Data Sources

* **NHTSA Complaints API** (`complaintsByVehicle`)
* **NHTSA Recalls API** (`recallsByVehicle`)
* **NHTSA vPIC VIN Decoder API**

The system ingests live federal data and stores it locally to enable fast, repeatable queries.

---

## Architecture

```
Streamlit UI (app.py)
        ↓
Query Layer (queries.py)
        ↓
SQLite ORM Models (database.py)
        ↓
Ingestion Layer (ingestion.py)
        ↓
NHTSA Public APIs
```

* `database.py` – Defines ORM models (Vehicle, Complaint, Recall) with deduplication constraints
* `ingestion.py` – Fetches and normalizes NHTSA data into SQLite
* `queries.py` – Performs aggregation and analytics queries
* `app.py` – Streamlit dashboard and intake workflow

The ingestion process is idempotent: running it multiple times does not create duplicate records.

---

## Setup

```bash
git clone <repo-url>
cd vehicle_defect_mvp
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
streamlit run app.py
```

---

## How It Works

1. Select lookup mode (VIN or make/model/year)
2. Click **ENTER** to fetch complaints and recalls
3. Review:

   * Complaint volume
   * Crash/fire/injury/death totals
   * Recall count and details
   * Top reported components
   * Complaint trends over time
   * Symptom search results

---

## Design Tradeoffs (MVP Scope)

* Components stored as text (not fully normalized)
* Symptom search uses simple substring matching (no semantic search)
* Recalls queried by make/model/year rather than VIN-specific recall endpoint
* SQLite chosen for portability and zero configuration

These decisions prioritize clarity, reliability, and delivery within an 8-hour build window.

---

## Future Improvements

* Normalize components into a dedicated table
* Add semantic search (embeddings / vector similarity)
* Integrate geographic analysis using bulk NHTSA complaint data
* Batch inserts for improved ingestion performance
* Deploy with PostgreSQL for production scalability

---

## Summary

This MVP demonstrates clean separation of ingestion, storage, querying, and presentation layers while leveraging authoritative federal defect data. It provides a practical foundation for a scalable vehicle defect intelligence platform.

