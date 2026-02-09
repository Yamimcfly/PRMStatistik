import os
import re
from typing import Optional
import pandas as pd

from app.db.models import ImportFile, DpaxDailySummary


def _simplify(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _find_header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(len(raw)):
        row = [str(v).strip() for v in raw.iloc[i].tolist()]
        if "Airline" in row and ("Ad-Hoc" in row or "Ad Hoc" in row):
            return i
    return None


def can_handle(path: str) -> bool:
    try:
        raw = pd.read_excel(path, sheet_name=0, header=None, nrows=60)
    except Exception:
        return False
    if _find_header_row(raw) is None:
        return False

    # Avoid matching Passenger Detail Report files that include a summary block.
    for i in range(len(raw)):
        row = [str(v).strip() for v in raw.iloc[i].tolist()]
        if "Operation Date" in row and "Request Airline" in row and "SSR Code" in row:
            return False
    return True


def load_dpax_summary(path: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=60)
    header_row = _find_header_row(raw)
    if header_row is None:
        raise ValueError("Header row not found for Dpax summary format.")

    df = pd.read_excel(path, sheet_name=0, header=header_row)
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    airline_col = None
    for col in df.columns:
        if _simplify(col) == "airline":
            airline_col = col
            break
    if not airline_col:
        raise ValueError("Airline column not found in Dpax summary.")

    df = df[df[airline_col].notna()].copy()
    date_col = df.columns[0]

    df = df.rename(columns={
        date_col: "report_date",
        airline_col: "airline",
        "Ad-Hoc": "ad_hoc",
        "Ad Hoc": "ad_hoc",
        "Planned": "planned",
    })

    return df


def import_dpax_summary(path: str, session) -> int:
    existing = session.query(ImportFile).filter(ImportFile.source_file == path).first()
    if existing:
        session.query(DpaxDailySummary).filter(DpaxDailySummary.import_id == existing.id).delete()
        session.delete(existing)
        session.flush()

    df = load_dpax_summary(path)
    month_key = None
    base = os.path.basename(path)
    match = re.search(r"_(\d{2})_(\d{4})", base)
    if match:
        month_key = f"{match.group(2)}-{match.group(1)}"
    elif df["report_date"].notna().any():
        month_key = pd.to_datetime(df["report_date"], errors="coerce").dropna().iloc[0].strftime("%Y-%m")
    else:
        month_key = base[:7] if len(base) >= 7 else "unknown"

    import_file = ImportFile(
        source_file=path,
        month_key=month_key or "unknown",
        source_system="DPAX_SUMMARY",
    )
    session.add(import_file)
    session.flush()

    def to_int(value):
        if value is None or pd.isna(value):
            return None
        try:
            return int(round(float(value)))
        except Exception:
            return None

    rows = []
    for _, row in df.iterrows():
        rows.append(
            DpaxDailySummary(
                import_id=import_file.id,
                report_date=pd.to_datetime(row.get("report_date"), errors="coerce").date() if row.get("report_date") else None,
                airline=str(row.get("airline")).strip() if row.get("airline") is not None else None,
                blnd=to_int(row.get("BLND")),
                deaf=to_int(row.get("DEAF")),
                deafblnd=to_int(row.get("DEAFBLND")),
                dpax_noshow=to_int(row.get("Dpax NoShow")),
                dpna=to_int(row.get("DPNA")),
                maas=to_int(row.get("MAAS")),
                meda=to_int(row.get("MEDA")),
                preboard=to_int(row.get("PREBOARD")),
                prebrdhs=to_int(row.get("PREBRDHS")),
                stcr=to_int(row.get("STCR")),
                wcbd=to_int(row.get("WCBD")),
                wcbw=to_int(row.get("WCBW")),
                wchc=to_int(row.get("WCHC")),
                wchr=to_int(row.get("WCHR")),
                wchs=to_int(row.get("WCHS")),
                wcmp=to_int(row.get("WCMP")),
                total_wch=to_int(row.get("Total")),
                ad_hoc=to_int(row.get("ad_hoc")),
                planned=to_int(row.get("planned")),
                total_overall=to_int(row.get("Total.1")),
            )
        )

    session.add_all(rows)
    return len(rows)
