import argparse
from pathlib import Path

import pandas as pd

from app.db.session import init_db, SessionLocal
from app.db.models import PrmAnnouncement, ImportFile


def export_unmapped_flights(output_path: Path) -> int:
    init_db()
    session = SessionLocal()
    try:
        rows = (
            session.query(
                PrmAnnouncement.airline_code,
                PrmAnnouncement.airline_raw,
                PrmAnnouncement.flight_no,
                PrmAnnouncement.flight_date,
                PrmAnnouncement.in_out,
                PrmAnnouncement.airport,
                PrmAnnouncement.airport_code,
                ImportFile.month_key,
                ImportFile.source_file,
            )
            .join(ImportFile, ImportFile.id == PrmAnnouncement.import_id, isouter=True)
            .filter(PrmAnnouncement.flight_no.isnot(None))
            .filter(PrmAnnouncement.flight_no != "")
            .filter(PrmAnnouncement.airport_code.is_(None))
            .all()
        )

        df = pd.DataFrame(
            rows,
            columns=[
                "airline_code",
                "airline_raw",
                "flight_no",
                "flight_date",
                "in_out",
                "airport_raw",
                "airport_code",
                "month_key",
                "source_file",
            ],
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if df.empty:
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                pd.DataFrame({"message": ["No unmapped flights found"]}).to_excel(
                    writer, sheet_name="Unmapped", index=False
                )
            return 0

        summary = (
            df.groupby(["airline_code", "airline_raw", "flight_no", "flight_date", "in_out"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["flight_date", "airline_code", "flight_no"], ascending=[True, True, True])
        )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="Unmapped", index=False)

        return len(summary)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export unmapped flight numbers to Excel")
    parser.add_argument(
        "--output",
        required=True,
        help="Output Excel path, e.g. C:/temp/unmapped_flights.xlsx",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    count = export_unmapped_flights(output_path)
    print(f"Exported {count} rows to {output_path}")


if __name__ == "__main__":
    main()
