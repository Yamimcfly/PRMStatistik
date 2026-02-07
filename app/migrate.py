from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL, SQLITE_SOURCE_URL, MIGRATION_OVERWRITE
from app.db.session import Base
from app.db.models import (
    ImportFile,
    PrmRequest,
    RefAirport,
    RefAirline,
    PrmAnnouncement,
    DpaxDailySummary,
)


def _copy_table(src_session, dst_session, model) -> int:
    rows = src_session.query(model).all()
    if not rows:
        return 0
    data = []
    for row in rows:
        item = {col.name: getattr(row, col.name) for col in model.__table__.columns}
        data.append(item)
    dst_session.bulk_insert_mappings(model, data)
    return len(data)


def migrate_sqlite_to_postgres(overwrite_target: bool = False) -> None:
    src_engine = create_engine(SQLITE_SOURCE_URL, future=True)
    dst_engine = create_engine(DATABASE_URL, future=True)

    Base.metadata.create_all(dst_engine)

    SrcSession = sessionmaker(bind=src_engine, future=True)
    DstSession = sessionmaker(bind=dst_engine, future=True)

    src_session = SrcSession()
    dst_session = DstSession()
    try:
        if not overwrite_target:
            existing = dst_session.query(ImportFile).first()
            if existing:
                raise RuntimeError("Target database already contains data. Set overwrite_target to true to proceed.")

        order = [
            ImportFile,
            RefAirport,
            RefAirline,
            PrmRequest,
            PrmAnnouncement,
            DpaxDailySummary,
        ]

        for model in order:
            _copy_table(src_session, dst_session, model)

        dst_session.commit()
    except Exception:
        dst_session.rollback()
        raise
    finally:
        src_session.close()
        dst_session.close()


if __name__ == "__main__":
    migrate_sqlite_to_postgres(overwrite_target=MIGRATION_OVERWRITE)
