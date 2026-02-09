from typing import Optional, Tuple

from app.db.models import RefFlightNumberFix
from app.importers.airline_mapping import normalize_airline_key
from app.importers.flight_destination_mapping import normalize_flight_no


def apply_flight_number_fix(
    airline_value: Optional[str],
    flight_no: Optional[str],
    session,
) -> Tuple[Optional[str], Optional[str]]:
    if not airline_value or not flight_no:
        return airline_value, flight_no
    airline_key = normalize_airline_key(str(airline_value))
    flight_key = normalize_flight_no(str(flight_no))
    if not airline_key or not flight_key:
        return airline_value, flight_no
    fix = session.get(RefFlightNumberFix, (airline_key, flight_key))
    if not fix:
        return airline_value, flight_no
    corrected_airline = fix.corrected_airline or airline_value
    corrected_flight_no = fix.corrected_flight_no or flight_no
    return corrected_airline, corrected_flight_no
