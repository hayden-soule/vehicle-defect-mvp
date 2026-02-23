# SLP Vehicle Defect Pattern Intelligence Tool (MVP)

LIVE DEMO: https://vehicle-defect-mvp-ybs4hwhle89fzyhapp9qjrp.streamlit.app/

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


## Data Sources

* **NHTSA Complaints API** (`complaintsByVehicle`)
* **NHTSA Recalls API** (`recallsByVehicle`)
* **NHTSA vPIC VIN Decoder API**

The system ingests live federal data and stores it locally to enable fast, repeatable queries.


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


## Design Tradeoffs (MVP Scope)

* Components stored as text (not fully normalized)
* Symptom search uses simple substring matching (no semantic search)
* SQLite chosen for portability and zero configuration
* Used API instead of flat-file to access NHTSA data (API turned out to lack geographic information)

These decisions prioritize clarity, reliability, and delivery within an 8-hour build window.


## Future Improvements

* Add semantic search (embeddings / vector similarity)
* Incorporate geographic analysis using flat-file integration of bulk NHTSA complaint data
* Batch inserts for improved ingestion performance
* Deploy with PostgreSQL for production scalability


## Use of AI Tools

AI tools were used during development to accelerate implementation, clarify architectural decisions, and improve documentation quality. The following describes how they were used:

### ChatGPT (OpenAI)

ChatGPT was used as a development assistant for:

* Designing the overall project structure (separating ingestion, schema, query, and UI layers)
* Clarifying NHTSA API response formats
* Debugging SQLAlchemy queries and Streamlit integration issues
* Improving error handling and resilience in ingestion logic

All generated code was reviewed, tested locally, and iteratively modified to ensure correctness and alignment with the project requirements.

### How AI Was Integrated Into the Workflow

AI tools were used in an iterative development loop:

1. Define feature goal (e.g., “add VIN lookup”)
2. Use AI to generate a rough implementation outline
3. Integrate into project manually
4. Test locally
5. Debug errors and refine logic
6. Add comments and documentation for clarity

The final structure, error handling decisions, and architectural tradeoffs reflect deliberate design choices rather than unedited AI output.
All code in the repository has been validated through manual testing and functional verification.


## Summary

This MVP demonstrates clean separation of ingestion, storage, querying, and presentation layers while leveraging federal vehicle defect data. It provides a practical foundation for a scalable vehicle defect intelligence platform.
