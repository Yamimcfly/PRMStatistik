import logging
import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError, DatabaseError

logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

class DatabaseConnectionError(Exception):
    """Custom exception für Datenbankverbindungsfehler mit benutzerfreundlicher Nachricht"""
    def __init__(self, message, technical_details=None):
        self.message = message
        self.technical_details = technical_details
        super().__init__(message)

def _create_engine_with_validation(database_url=None, skip_validation=False):
    """
    Erstellt SQLAlchemy Engine mit Verbindungsvalidierung.
    Gibt hilfreiche Fehlermeldungen aus, falls die Verbindung fehlschlägt.
    
    Args:
        database_url: Optional, überschreibt die DATABASE_URL aus config
        skip_validation: Wenn True, wird die Verbindung nicht getestet
    """
    if database_url is None:
        from app.config import DATABASE_URL
        database_url = DATABASE_URL
    
    try:
        engine = create_engine(database_url, future=True)
        
        if not skip_validation:
            # Verbindung testen
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        
        db_type = {
            "postgresql": "PostgreSQL",
            "sqlite": "SQLite",
            "mysql": "MySQL",
            "mssql": "SQL Server"
        }.get(engine.dialect.name, engine.dialect.name.title())
        logger.info(f"Datenbankverbindung erfolgreich hergestellt ({db_type})")
        
        return engine
    
    except OperationalError as e:
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        user_message = "Datenbankverbindung fehlgeschlagen"
        
        if "could not connect" in error_msg.lower() or "connection refused" in error_msg.lower():
            user_message = (
                "Datenbankserver nicht erreichbar.\n\n"
                "Bitte überprüfen Sie:\n"
                "• DATABASE_URL in .env oder config.json ist korrekt\n"
                "• Netzwerkverbindung zum Datenbankserver\n"
                "• Firewall-Einstellungen"
            )
        elif "authentication failed" in error_msg.lower() or "password" in error_msg.lower():
            user_message = (
                "Authentifizierung fehlgeschlagen.\n\n"
                "Bitte überprüfen Sie:\n"
                "• Benutzername und Passwort in DATABASE_URL\n"
                "• Neon-Zugangsdaten sind aktuell"
            )
        elif "ssl" in error_msg.lower() or "tls" in error_msg.lower():
            user_message = (
                "SSL/TLS-Verbindung fehlgeschlagen.\n\n"
                "Für Neon PostgreSQL muss die DATABASE_URL mit ?sslmode=require enden.\n"
                "Beispiel: postgresql://user:pass@endpoint.neon.tech/db?sslmode=require"
            )
        elif "does not exist" in error_msg.lower():
            user_message = (
                "Datenbank existiert nicht.\n\n"
                "Bitte erstellen Sie die Datenbank in Neon oder überprüfen Sie den Datenbanknamen."
            )
        elif "unable to open database file" in error_msg.lower():
            user_message = (
                "SQLite-Datenbank konnte nicht geöffnet werden.\n\n"
                "Bitte stellen Sie sicher, dass:\n"
                "• Das Verzeichnis existiert\n"
                "• Sie Schreibrechte haben"
            )
        
        logger.error(f"{user_message}\nDetails: {error_msg}")
        raise DatabaseConnectionError(user_message, error_msg)
    
    except DatabaseError as e:
        error_msg = str(e)
        logger.error(f"Datenbankfehler: {error_msg}")
        raise DatabaseConnectionError(f"Datenbankfehler: {error_msg}", error_msg)
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unerwarteter Fehler beim Erstellen der Datenbankverbindung: {error_msg}")
        raise DatabaseConnectionError(
            f"Unerwarteter Fehler beim Erstellen der Datenbankverbindung",
            error_msg
        )

# Engine und Session werden beim Import erstellt
# Im GUI-Modus kann dies durch einen try-except-Block abgefangen werden
_engine = None
SessionLocal = None

def initialize_database(database_url=None):
    """
    Initialisiert die Datenbank-Engine und Session.
    Kann von der GUI aufgerufen werden, um die Datenbank nach Benutzereingabe zu initialisieren.
    """
    global _engine, SessionLocal
    _engine = _create_engine_with_validation(database_url)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine

# Versuche, die Datenbank beim Import zu initialisieren
# Wenn dies fehlschlägt, muss die GUI initialize_database() aufrufen
try:
    _engine = _create_engine_with_validation()
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
except DatabaseConnectionError as e:
    # Im GUI-Modus wird dies abgefangen
    logger.warning(f"Datenbankverbindung beim Import fehlgeschlagen: {e.message}")
    logger.info("GUI wird aufgefordert, Datenbankverbindung zu konfigurieren")
except Exception as e:
    # Unerwartete Fehler loggen, aber nicht abbrechen
    logger.warning(f"Fehler beim Initialisieren der Datenbank: {e}")
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
