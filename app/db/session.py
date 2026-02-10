import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError, DatabaseError
from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

def _create_engine_with_validation():
    """
    Erstellt SQLAlchemy Engine mit Verbindungsvalidierung.
    Gibt hilfreiche Fehlermeldungen aus, falls die Verbindung fehlschlägt.
    """
    try:
        engine = create_engine(DATABASE_URL, future=True)
        
        # Verbindung testen
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        db_type = "PostgreSQL" if engine.dialect.name == "postgresql" else engine.dialect.name.upper()
        logger.info(f"Datenbankverbindung erfolgreich hergestellt ({db_type})")
        
        return engine
    
    except OperationalError as e:
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        
        if "could not connect" in error_msg.lower() or "connection refused" in error_msg.lower():
            logger.error(
                f"Datenbankverbindung fehlgeschlagen: Server nicht erreichbar.\n"
                f"Bitte überprüfen Sie:\n"
                f"  - DATABASE_URL in .env oder config.json ist korrekt\n"
                f"  - Netzwerkverbindung zum Datenbankserver\n"
                f"  - Firewall-Einstellungen\n"
                f"Details: {error_msg}"
            )
        elif "authentication failed" in error_msg.lower() or "password" in error_msg.lower():
            logger.error(
                f"Datenbankverbindung fehlgeschlagen: Authentifizierung ungültig.\n"
                f"Bitte überprüfen Sie:\n"
                f"  - Benutzername und Passwort in DATABASE_URL\n"
                f"  - Neon-Zugangsdaten sind aktuell\n"
                f"Details: {error_msg}"
            )
        elif "ssl" in error_msg.lower() or "tls" in error_msg.lower():
            logger.error(
                f"Datenbankverbindung fehlgeschlagen: SSL/TLS-Problem.\n"
                f"Für Neon PostgreSQL muss die DATABASE_URL mit ?sslmode=require enden.\n"
                f"Beispiel: postgresql://user:pass@endpoint.neon.tech/db?sslmode=require\n"
                f"Details: {error_msg}"
            )
        elif "does not exist" in error_msg.lower():
            logger.error(
                f"Datenbankverbindung fehlgeschlagen: Datenbank existiert nicht.\n"
                f"Bitte erstellen Sie die Datenbank in Neon oder überprüfen Sie den Datenbanknamen.\n"
                f"Details: {error_msg}"
            )
        else:
            logger.error(f"Datenbankverbindung fehlgeschlagen: {error_msg}")
        
        raise
    
    except DatabaseError as e:
        logger.error(f"Datenbankfehler: {e}")
        raise
    
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Erstellen der Datenbankverbindung: {e}")
        raise

_engine = _create_engine_with_validation()
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
