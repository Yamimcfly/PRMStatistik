import re
from typing import Optional

from app.db.models import RefFlightDestination, PrmAnnouncement
from app.importers.airline_mapping import normalize_airline_key


def normalize_flight_no(value: str) -> str:
    text = value.strip().upper()
    text = text.replace("D:", "").replace("A:", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^A-Z0-9]", "", text)
    return text


def map_flight_destination(airline_value: Optional[str], flight_no: Optional[str], session) -> Optional[str]:
    if not airline_value or not flight_no:
        return None
    airline_key = normalize_airline_key(str(airline_value))
    flight_key = normalize_flight_no(str(flight_no))
    if not airline_key or not flight_key:
        return None
    found = session.get(RefFlightDestination, (airline_key, flight_key))
    if found and found.destination_iata3:
        return found.destination_iata3
    return None


def build_flight_destination_map(session) -> int:
    rows = session.query(
        PrmAnnouncement.airline_code,
        PrmAnnouncement.airline_raw,
        PrmAnnouncement.flight_no,
        PrmAnnouncement.airport_code,
    ).filter(
        PrmAnnouncement.flight_no.isnot(None),
        PrmAnnouncement.airport_code.isnot(None),
    ).all()

    entries = {}
    for airline_code, airline_raw, flight_no, airport_code in rows:
        airline_value = airline_code or airline_raw
        if not airline_value or not flight_no or not airport_code:
            continue
        airline_key = normalize_airline_key(str(airline_value))
        flight_key = normalize_flight_no(str(flight_no))
        if not airline_key or not flight_key:
            continue
        entries[(airline_key, flight_key)] = airport_code

    updated = 0
    for (airline_key, flight_key), dest in entries.items():
        session.merge(
            RefFlightDestination(
                airline_key=airline_key,
                flight_no_key=flight_key,
                destination_iata3=dest,
                mapping_source="auto",
            )
        )
        updated += 1
    return updated
