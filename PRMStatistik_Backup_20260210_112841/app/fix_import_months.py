import re
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL
from app.db.models import ImportFile


def _month_from_filename(path: str) -> str | None:
    match = re.search(r"_(\d{2})_(\d{4})", path)
    if not match:
        return None
    return f"{match.group(2)}-{match.group(1)}"


def fix_month_keys() -> int:
    engine = create_engine(DATABASE_URL, future=True)
    Session = sessionmaker(bind=engine, future=True)

    updated = 0
    with Session() as session:
        rows = session.execute(select(ImportFile)).scalars().all()
        for row in rows:
            new_key = _month_from_filename(row.source_file or "")
            if new_key and row.month_key != new_key:
                row.month_key = new_key
                updated += 1
        if updated:
            session.commit()
    return updated


if __name__ == "__main__":
    count = fix_month_keys()
    print(f"Updated month_key for {count} imports")
