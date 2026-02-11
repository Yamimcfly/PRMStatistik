from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL, WCH_MAPPING_FILE
from app.db.models import PrmAnnouncement
from app.importers.wch_mapping import load_wch_mapping, map_wch_category


def backfill_wch_categories() -> int:
    engine = create_engine(DATABASE_URL, future=True)
    Session = sessionmaker(bind=engine, future=True)

    updated = 0
    with Session() as session:
        if WCH_MAPPING_FILE:
            load_wch_mapping(WCH_MAPPING_FILE, session)
        rows = session.query(PrmAnnouncement).filter(PrmAnnouncement.wch_category.is_(None)).all()
        for row in rows:
            row.wch_category = map_wch_category(row.wch_type, session)
            if row.wch_category:
                updated += 1
        if updated:
            session.commit()
    return updated


if __name__ == "__main__":
    count = backfill_wch_categories()
    print(f"Updated WCH categories for {count} rows")
