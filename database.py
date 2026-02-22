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

DATABASE_URL = "sqlite:///slp_defects.db"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=False)

    complaints = relationship("Complaint", back_populates="vehicle", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("make", "model", "year", name="uq_vehicle"),)


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)

    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)

    odi_number = Column(String, nullable=False)  # NHTSA complaint id
    manufacturer = Column(String, nullable=True)

    crash = Column(Boolean, nullable=True)
    fire = Column(Boolean, nullable=True)
    number_of_injuries = Column(Integer, nullable=True)
    number_of_deaths = Column(Integer, nullable=True)

    date_of_incident = Column(Date, nullable=True)
    date_complaint_filed = Column(Date, nullable=True)

    vin = Column(String, nullable=True)
    components = Column(Text, nullable=True)  # store as comma-separated string for MVP
    summary = Column(Text, nullable=True)

    # “products” is sometimes a list; store as text for MVP
    products = Column(Text, nullable=True)

    vehicle = relationship("Vehicle", back_populates="complaints")

    __table_args__ = (UniqueConstraint("odi_number", name="uq_complaint_odi"),)


def init_db():
    Base.metadata.create_all(engine)