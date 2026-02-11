"""
Zeigt vollständigen Mapping-Status der Datenbank
"""
import sys
sys.path.insert(0, '.')

from app.db.session import SessionLocal
from app.db.models import (
    PrmAnnouncement, RefAirlineMap, RefDestination, 
    RefFlightDestination, RefWchType
)
from app.importers.airline_mapping import map_airline
from app.importers.destination_mapping import map_destination
from app.importers.flight_destination_mapping import map_flight_destination
from app.importers.wch_mapping import map_wch_category

session = SessionLocal()
try:
    print("=" * 70)
    print("MAPPING STATUS - Übersicht")
    print("=" * 70)
    
    # Airline Mapping
    print("\n1. AIRLINE MAPPING")
    print("-" * 70)
    airline_mappings = session.query(RefAirlineMap).count()
    print(f"   Gespeicherte Airline-Mappings: {airline_mappings}")
    
    airline_values = session.query(
        PrmAnnouncement.airline_raw, 
        PrmAnnouncement.airline_code
    ).distinct().all()
    
    unmapped_airlines = []
    for raw_val, code_val in airline_values:
        source = code_val or raw_val
        if source and map_airline(source, session) is None:
            unmapped_airlines.append(str(source))
    
    unmapped_airlines = sorted(set(unmapped_airlines))
    print(f"   Nicht zugeordnete Airlines: {len(unmapped_airlines)}")
    if unmapped_airlines[:5]:
        print(f"   Beispiele: {', '.join(unmapped_airlines[:5])}")
    
    # Flight Destination Mapping
    print("\n2. FLUGNUMMER → DESTINATION MAPPING")
    print("-" * 70)
    flight_mappings = session.query(RefFlightDestination).count()
    print(f"   Gespeicherte Flight-Mappings: {flight_mappings}")
    
    values = session.query(
        PrmAnnouncement.airline_raw,
        PrmAnnouncement.airline_code,
        PrmAnnouncement.flight_no,
        PrmAnnouncement.airport_code,
    ).filter(PrmAnnouncement.flight_no.isnot(None)).distinct().all()
    
    unmapped_flights = []
    with_airport = 0
    
    for raw_val, code_val, flight_no, airport_code in values:
        if airport_code:
            with_airport += 1
            continue
        
        airline_value = code_val or raw_val
        if not airline_value:
            continue
        
        if map_flight_destination(airline_value, flight_no, session) is None:
            unmapped_flights.append((str(airline_value), str(flight_no)))
    
    unmapped_flights = sorted(set(unmapped_flights))
    print(f"   Bereits mit Destination: {with_airport}")
    print(f"   Nicht zugeordnete Flugnummern: {len(unmapped_flights)}")
    if unmapped_flights[:5]:
        examples = [f"{a} {f}" for a, f in unmapped_flights[:5]]
        print(f"   Beispiele: {', '.join(examples)}")
    
    # Destination Mapping
    print("\n3. DESTINATION MAPPING")
    print("-" * 70)
    dest_mappings = session.query(RefDestination).count()
    print(f"   Gespeicherte Destination-Mappings: {dest_mappings}")
    
    dest_values = session.query(PrmAnnouncement.airport).distinct().all()
    unmapped_dest = []
    for (dest_val,) in dest_values:
        if dest_val and map_destination(dest_val, session) is None:
            unmapped_dest.append(str(dest_val))
    
    unmapped_dest = sorted(set(unmapped_dest))
    print(f"   Nicht zugeordnete Destinations: {len(unmapped_dest)}")
    if unmapped_dest[:5]:
        print(f"   Beispiele: {', '.join(unmapped_dest[:5])}")
    
    # WCH Mapping
    print("\n4. WCH KATEGORIE MAPPING")
    print("-" * 70)
    wch_mappings = session.query(RefWchType).count()
    print(f"   Gespeicherte WCH-Mappings: {wch_mappings}")
    
    wch_values = session.query(PrmAnnouncement.wch_type).distinct().all()
    unmapped_wch = []
    for (wch_val,) in wch_values:
        if wch_val and map_wch_category(wch_val, session) is None:
            unmapped_wch.append(str(wch_val))
    
    unmapped_wch = sorted(set(unmapped_wch))
    print(f"   Nicht zugeordnete WCH-Typen: {len(unmapped_wch)}")
    if unmapped_wch[:5]:
        print(f"   Beispiele: {', '.join(unmapped_wch[:5])}")
    
    # Datenbank-Statistik
    print("\n5. DATENBANK-STATISTIK")
    print("-" * 70)
    total_announcements = session.query(PrmAnnouncement).count()
    print(f"   Gesamt PRM-Meldungen: {total_announcements}")
    
    with_flight = session.query(PrmAnnouncement).filter(
        PrmAnnouncement.flight_no.isnot(None)
    ).count()
    print(f"   Meldungen mit Flugnummer: {with_flight}")
    
    with_airport_code = session.query(PrmAnnouncement).filter(
        PrmAnnouncement.airport_code.isnot(None)
    ).count()
    print(f"   Meldungen mit Zielflughafen-Code: {with_airport_code}")
    
    print("\n" + "=" * 70)
    
finally:
    session.close()
