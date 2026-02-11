from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL, DESTINATION_MAPPING_FILE
from app.db.models import PrmAnnouncement
from app.db.session import init_db
from app.importers.destination_mapping import load_destination_mapping, map_destination


def backfill_destination_codes() -> int:
    init_db()
    engine = create_engine(DATABASE_URL, future=True)
    Session = sessionmaker(bind=engine, future=True)

    updated = 0
    with Session() as session:
        if DESTINATION_MAPPING_FILE:
            load_destination_mapping(DESTINATION_MAPPING_FILE, session)
        rows = session.query(PrmAnnouncement).filter(PrmAnnouncement.airport_code.is_(None)).all()
        for row in rows:
            row.airport_code = map_destination(row.airport, session)
            if row.airport_code:
                updated += 1
        if updated:
            session.commit()
    return updated


if __name__ == "__main__":
    count = backfill_destination_codes()
    print(f"Updated destination codes for {count} rows")
