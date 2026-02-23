"""
database.py

Purpose:
- Defines the local persistence layer for the MVP using SQLite + SQLAlchemy ORM.
- The app pulls raw data from NHTSA APIs (complaints + recalls) and caches it locally
  so the dashboard can run fast queries without repeatedly hitting external endpoints.

Design notes (MVP tradeoffs):
- The schema is intentionally small and practical:
  * Vehicle: one row per (make, model, year)
  * Complaint: one row per NHTSA ODI complaint (deduped by ODI number)
  * Recall: one row per NHTSA recall campaign for that vehicle (deduped by campaign number)
- Some nested/complex fields from the APIs (e.g., "components", "products") are stored as text
  for speed of implementation. A production version could normalize these into separate tables.
"""

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


# SQLite file stored in the project directory.
# This is the application's "cache" of NHTSA data for fast, repeatable analysis.
DATABASE_URL = "sqlite:///slp_defects.db"

# SQLAlchemy engine + session factory.
# "future=True" opts into SQLAlchemy 2.0 style behaviors.
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Base class used by SQLAlchemy to construct ORM models.
Base = declarative_base()


class Vehicle(Base):
    """
    Normalized vehicle identity used throughout the app.
    One row represents a unique (make, model, year) combination.

    In a VIN-centric version, the VIN itself could become a first-class entity,
    but for the MVP we decode VIN → make/model/year and reuse this table.
    """
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)

    # Stored as uppercase in ingestion to keep lookups consistent.
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=False)

    # Relationships enable simple navigation (vehicle.complaints / vehicle.recalls)
    # and cascading deletes for local cleanup during development.
    complaints = relationship(
        "Complaint", back_populates="vehicle", cascade="all, delete-orphan"
    )
    recalls = relationship(
        "Recall", back_populates="vehicle", cascade="all, delete-orphan"
    )

    # Prevent duplicate vehicles (e.g., repeated ingestion clicks).
    __table_args__ = (UniqueConstraint("make", "model", "year", name="uq_vehicle"),)


class Complaint(Base):
    """
    Stores consumer complaints from NHTSA's ODI complaint database.

    Key fields are mapped from the complaintsByVehicle endpoint:
    - odi_number: NHTSA complaint identifier (unique)
    - crash/fire/injuries/deaths: severity indicators used to assess case strength
    - components/summary: used to identify defect patterns and support symptom search
    """
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)

    # Foreign key ties a complaint to a specific vehicle definition (make/model/year).
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)

    # ODI complaint id is the natural unique identifier in the NHTSA system.
    odi_number = Column(String, nullable=False)
    manufacturer = Column(String, nullable=True)

    # Severity indicators (important for legal case strength triage).
    crash = Column(Boolean, nullable=True)
    fire = Column(Boolean, nullable=True)
    number_of_injuries = Column(Integer, nullable=True)
    number_of_deaths = Column(Integer, nullable=True)

    # NHTSA typically provides dates as strings; ingestion parses to Python date objects.
    date_of_incident = Column(Date, nullable=True)
    date_complaint_filed = Column(Date, nullable=True)

    # VIN can appear in the complaint record depending on endpoint payload.
    # The MVP does not treat VIN as a primary key; it is stored as an attribute.
    vin = Column(String, nullable=True)

    # MVP tradeoff: "components" is stored as a comma-separated string for easy display.
    # A more advanced version would normalize components into a separate table for better analytics.
    components = Column(Text, nullable=True)

    # Short narrative/summary used for symptom search and qualitative review.
    summary = Column(Text, nullable=True)

    # Some API fields can be lists/dicts ("products"); store raw-ish text for MVP.
    products = Column(Text, nullable=True)

    # Relationship back to vehicle.
    vehicle = relationship("Vehicle", back_populates="complaints")

    # Deduplication constraint:
    # Running ingestion multiple times should not create duplicates.
    __table_args__ = (UniqueConstraint("odi_number", name="uq_complaint_odi"),)


class Recall(Base):
    """
    Stores safety recall campaigns from NHTSA's recall database.

    Primary identifier for a recall is the NHTSA Campaign Number.
    Recalls are associated with a Vehicle (make/model/year) for this MVP.
    """
    __tablename__ = "recalls"

    id = Column(Integer, primary_key=True)

    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)

    # NHTSA campaign number uniquely identifies a recall campaign.
    campaign_number = Column(String, nullable=False)

    # Some payloads include a manufacturer recall number as well.
    recall_number = Column(String, nullable=True)

    # When NHTSA received the report (useful for timeline/trends).
    report_received_date = Column(Date, nullable=True)

    component = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    consequence = Column(Text, nullable=True)
    remedy = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    vehicle = relationship("Vehicle", back_populates="recalls")

    # Deduplication constraint:
    # Same vehicle should not store the same campaign twice.
    __table_args__ = (
        UniqueConstraint("vehicle_id", "campaign_number", name="uq_vehicle_campaign"),
    )


def init_db():
    """
    Creates tables if they do not exist.

    Note for reviewers:
    - This does NOT run schema migrations (SQLite + create_all only creates missing tables).
    - During MVP development, if columns/tables change, deleting the SQLite file is the simplest reset.
    """
    Base.metadata.create_all(engine)