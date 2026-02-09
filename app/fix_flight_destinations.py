from app.db.session import init_db, SessionLocal
from app.db.models import PrmAnnouncement
from app.importers.flight_destination_mapping import (
    build_flight_destination_map,
    map_flight_destination,
)


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        built = build_flight_destination_map(session)
        updated = 0
        rows = session.query(PrmAnnouncement).all()
        for row in rows:
            if row.airport_code:
                continue
            airline_value = row.airline_code or row.airline_raw
            mapped = map_flight_destination(airline_value, row.flight_no, session)
            if mapped:
                row.airport_code = mapped
                updated += 1
        session.commit()
        print(f"Built {built} flight mappings")
        print(f"Updated {updated} announcements")
    finally:
        session.close()


if __name__ == "__main__":
    main()
