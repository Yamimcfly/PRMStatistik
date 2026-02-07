import os
import re
from typing import Optional
import pandas as pd

from app.importers.wch_mapping import map_wch_category
from app.importers.destination_mapping import map_destination

from app.db.models import ImportFile, PrmAnnouncement


def _simplify(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _find_col(df: pd.DataFrame, name: str, aliases: Optional[list[str]] = None) -> Optional[str]:
    targets = {_simplify(name)}
    for alias in aliases or []:
        targets.add(_simplify(alias))
    for col in df.columns:
        if _simplify(str(col)) in targets:
            return col
    return None


def _find_header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(len(raw)):
        row = [str(v).strip() for v in raw.iloc[i].tolist()]
        if "FlugNr." in row and "E-Datum" in row:
            return i
    return None


def can_handle(path: str) -> bool:
    try:
        raw = pd.read_excel(path, sheet_name=0, header=None, nrows=20)
    except Exception:
        return False
    return _find_header_row(raw) is not None


def _lead_bucket(row: pd.Series, lead_hours: Optional[float]) -> Optional[str]:
    def is_one(col_name: str) -> bool:
        value = row.get(col_name)
        try:
            return float(value) == 1.0
        except Exception:
            return False

    if is_one("< 1 h") or is_one("1-3 h") or is_one("3 - 36 h") or is_one("alle unter 36"):
        return "adhoc"
    if is_one("> 36 h"):
        return "planned"
    if lead_hours is None:
        return None
    return "adhoc" if lead_hours < 36 else "planned"


def load_voranmeldungen(path: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=50)
    header_row = _find_header_row(raw)
    if header_row is None:
        raise ValueError("Header row not found for Voranmeldungen format.")

    df = pd.read_excel(path, sheet_name=0, header=header_row)
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    col_airline = _find_col(df, "LVG")
    col_handling = _find_col(df, "Handlingsges.")
    col_flight_no = _find_col(df, "FlugNr.")
    col_flight_date = _find_col(df, "E-Datum")
    col_flight_time = _find_col(df, "Zeit")
    col_report_date = _find_col(df, "M. am")
    col_report_time = _find_col(df, "M. um")
    col_lead_hours = _find_col(df, "Stunden")
    col_airport = _find_col(df, "von Airport")
    col_wch = _find_col(df, "WCH Art")
    col_late = _find_col(df, "Spätmeldung", aliases=["Spaetmeldung", "Sp�tmeldung"])
    col_no_pax = _find_col(df, "kein Pax")
    col_inout = _find_col(df, "InOut")

    df = df[df[col_flight_no].notna()].copy() if col_flight_no else df.copy()

    lead_hours = pd.to_numeric(df[col_lead_hours], errors="coerce") if col_lead_hours else None

    normalized = pd.DataFrame({
        "airline_code": df[col_airline].astype(str).str.strip() if col_airline else None,
        "handling_company": df[col_handling].astype(str).str.strip() if col_handling else None,
        "flight_no": df[col_flight_no].astype(str).str.strip() if col_flight_no else None,
        "flight_date": pd.to_datetime(df[col_flight_date], errors="coerce", dayfirst=True).dt.date if col_flight_date else None,
        "flight_time": df[col_flight_time].astype(str).str.strip() if col_flight_time else None,
        "report_date": pd.to_datetime(df[col_report_date], errors="coerce", dayfirst=True).dt.date if col_report_date else None,
        "report_time": df[col_report_time].astype(str).str.strip() if col_report_time else None,
        "lead_hours": lead_hours,
        "airport": df[col_airport].astype(str).str.strip() if col_airport else None,
        "wch_type": df[col_wch].astype(str).str.strip() if col_wch else None,
        "late_report": df[col_late].astype(str).str.strip().str.lower().eq("ja") if col_late else False,
        "no_pax": df[col_no_pax].astype(str).str.strip().str.lower().eq("ja") if col_no_pax else False,
        "in_out": df[col_inout].astype(str).str.strip() if col_inout else None,
    })

    if lead_hours is not None:
        normalized["lead_bucket"] = [
            _lead_bucket(row, lead_hours.loc[idx])
            for idx, row in df.iterrows()
        ]
    else:
        normalized["lead_bucket"] = None

    normalized = normalized[normalized["wch_type"].notna()].copy()
    normalized["wch_type"] = normalized["wch_type"].replace({"nan": None}).astype(str).str.strip()
    return normalized


def import_voranmeldungen(path: str, session) -> int:
    existing = session.query(ImportFile).filter(ImportFile.source_file == path).first()
    if existing:
        session.query(PrmAnnouncement).filter(PrmAnnouncement.import_id == existing.id).delete()
        session.delete(existing)
        session.flush()

    df = load_voranmeldungen(path)
    month_key = None
    base = os.path.basename(path)
    match = re.search(r"_(\d{2})_(\d{4})", base)
    if match:
        month_key = f"{match.group(2)}-{match.group(1)}"
    elif df["flight_date"].notna().any():
        month_key = df["flight_date"].dropna().iloc[0].strftime("%Y-%m")
    else:
        month_key = base[:7] if len(base) >= 7 else "unknown"

    import_file = ImportFile(
        source_file=path,
        month_key=month_key or "unknown",
        source_system="VORANMELDUNGEN",
    )
    session.add(import_file)
    session.flush()

    def to_none(value):
        return None if pd.isna(value) else value

    def safe_str(value, max_len: int | None = None):
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if text.lower() == "nan" or text == "":
            return None
        if max_len is not None and len(text) > max_len:
            return text[:max_len]
        return text

    rows = []
    for _, row in df.iterrows():
        rows.append(
            PrmAnnouncement(
                import_id=import_file.id,
                airline_code=safe_str(row.get("airline_code"), 5),
                handling_company=safe_str(row.get("handling_company"), 255),
                flight_no=safe_str(row.get("flight_no"), 20),
                flight_date=to_none(row.get("flight_date")),
                flight_time=safe_str(row.get("flight_time"), 10),
                report_date=to_none(row.get("report_date")),
                report_time=safe_str(row.get("report_time"), 10),
                lead_hours=to_none(row.get("lead_hours")),
                lead_bucket=safe_str(row.get("lead_bucket"), 20),
                airport=safe_str(row.get("airport"), 80),
                airport_code=map_destination(row.get("airport"), session),
                wch_type=safe_str(row.get("wch_type"), 10),
                wch_category=map_wch_category(row.get("wch_type"), session),
                late_report=bool(row.get("late_report")) if not pd.isna(row.get("late_report")) else False,
                no_pax=bool(row.get("no_pax")) if not pd.isna(row.get("no_pax")) else False,
                in_out=safe_str(row.get("in_out"), 20),
            )
        )

    session.add_all(rows)
    return len(rows)
