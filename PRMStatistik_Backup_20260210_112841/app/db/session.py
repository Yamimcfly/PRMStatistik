from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DATABASE_URL

class Base(DeclarativeBase):
    pass

_engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

def init_db():
    # Import models so metadata is populated
    from app.db import models  # noqa: F401
    Base.metadata.create_all(_engine)

    inspector = inspect(_engine)
    if inspector.has_table("prm_announcements"):
        columns = {c["name"] for c in inspector.get_columns("prm_announcements")}
        if "wch_category" not in columns:
            ddl = "ALTER TABLE prm_announcements ADD COLUMN wch_category TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE prm_announcements ADD COLUMN wch_category VARCHAR(20)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))
        if "airport_code" not in columns:
            ddl = "ALTER TABLE prm_announcements ADD COLUMN airport_code TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE prm_announcements ADD COLUMN airport_code VARCHAR(3)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))
        if "airline_raw" not in columns:
            ddl = "ALTER TABLE prm_announcements ADD COLUMN airline_raw TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE prm_announcements ADD COLUMN airline_raw VARCHAR(255)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))

    if inspector.has_table("ref_destination"):
        columns = {c["name"] for c in inspector.get_columns("ref_destination")}
        if "display_name" not in columns:
            ddl = "ALTER TABLE ref_destination ADD COLUMN display_name TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE ref_destination ADD COLUMN display_name VARCHAR(255)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))
        if "mapping_source" not in columns:
            ddl = "ALTER TABLE ref_destination ADD COLUMN mapping_source TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE ref_destination ADD COLUMN mapping_source VARCHAR(20)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))

    if inspector.has_table("ref_wch_type"):
        columns = {c["name"] for c in inspector.get_columns("ref_wch_type")}
        if "mapping_source" not in columns:
            ddl = "ALTER TABLE ref_wch_type ADD COLUMN mapping_source TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE ref_wch_type ADD COLUMN mapping_source VARCHAR(20)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))

    if inspector.has_table("ref_airline_map"):
        columns = {c["name"] for c in inspector.get_columns("ref_airline_map")}
        if "mapping_source" not in columns:
            ddl = "ALTER TABLE ref_airline_map ADD COLUMN mapping_source TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE ref_airline_map ADD COLUMN mapping_source VARCHAR(20)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))

    if inspector.has_table("ref_flight_destination"):
        columns = {c["name"] for c in inspector.get_columns("ref_flight_destination")}
        if "mapping_source" not in columns:
            ddl = "ALTER TABLE ref_flight_destination ADD COLUMN mapping_source TEXT"
            if _engine.dialect.name == "postgresql":
                ddl = "ALTER TABLE ref_flight_destination ADD COLUMN mapping_source VARCHAR(20)"
            with _engine.begin() as conn:
                conn.execute(text(ddl))
