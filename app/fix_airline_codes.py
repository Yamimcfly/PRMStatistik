from app.db.session import init_db, SessionLocal
from app.db.models import PrmAnnouncement
from app.importers.airline_mapping import map_airline


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        rows = session.query(PrmAnnouncement).all()
        updated = 0
        for row in rows:
            raw = row.airline_raw or row.airline_code
            if raw is None:
                continue
            mapped = map_airline(raw, session)
            if mapped and mapped != row.airline_code:
                row.airline_code = mapped
                if row.airline_raw is None:
                    row.airline_raw = str(raw)
                updated += 1
        session.commit()
        print(f"Updated {updated} airline codes")
    finally:
        session.close()


if __name__ == "__main__":
    main()
