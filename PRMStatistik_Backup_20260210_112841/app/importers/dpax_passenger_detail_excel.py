import os
import re
from typing import Optional
import pandas as pd

from app.db.models import ImportFile, PrmAnnouncement
from app.importers.airline_mapping import map_airline
from app.importers.wch_mapping import map_wch_category
from app.importers.destination_mapping import map_destination
from app.importers.flight_destination_mapping import map_flight_destination
from app.importers.flight_number_fix import apply_flight_number_fix
from app.services.parsing import parse_flight_number


def _simplify(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _find_header_row(raw: pd.DataFrame) -> Optional[int]:
    for i in range(len(raw)):
        row = [str(v).strip() for v in raw.iloc[i].tolist()]
        if "Operation Date" in row and "Request Airline" in row and "SSR Code" in row:
            return i
    return None


def can_handle(path: str) -> bool:
    try:
        raw = pd.read_excel(path, sheet_name=0, header=None, nrows=60)
    except Exception:
        return False
    return _find_header_row(raw) is not None


def load_detail_report(path: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None, nrows=80)
    header_row = _find_header_row(raw)
    if header_row is None:
        raise ValueError("Header row not found for Passenger Detail Report format.")

    df = pd.read_excel(path, sheet_name=0, header=header_row)
    df = df.dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]

    def find_col(name: str) -> Optional[str]:
        target = _simplify(name)
        for col in df.columns:
            if _simplify(col) == target:
                return col
        return None

    col_date = find_col("Operation Date")
    col_airline = find_col("Request Airline")
    col_flight_no = find_col("Flight Number")
    col_ssr = find_col("SSR Code")
    col_lead = find_col("Planned / Adhoc")
    col_inout = find_col("Arr/Con/Dep")

    normalized = pd.DataFrame({
        "flight_date": pd.to_datetime(df[col_date], errors="coerce").dt.date if col_date else None,
        "airline_raw": df[col_airline].astype(str).str.strip() if col_airline else None,
        "flight_no": df[col_flight_no].astype(str).str.strip() if col_flight_no else None,
        "wch_type": df[col_ssr].astype(str).str.strip() if col_ssr else None,
        "lead_bucket": df[col_lead].astype(str).str.strip().str.lower() if col_lead else None,
        "in_out": df[col_inout].astype(str).str.strip() if col_inout else None,
    })

    normalized = normalized[normalized["wch_type"].notna()].copy()
    normalized["wch_type"] = normalized["wch_type"].replace({"nan": None}).astype(str).str.strip()
    normalized["airline_raw"] = normalized["airline_raw"].replace({"nan": None})
    normalized["flight_no"] = normalized["flight_no"].replace({"nan": None})
    normalized["in_out"] = normalized["in_out"].replace({"nan": None})

    def split_flight_info(value: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        raw = value if value is None else str(value).strip()
        if not raw or raw.lower() == "nan":
            return None, None, None
        dir_code, carrier, number = parse_flight_number(raw)
        if carrier and number:
            flight_no = f"{carrier} {number}"
        else:
            flight_no = raw
        if dir_code == "D":
            in_out = "Dep"
        elif dir_code == "A":
            in_out = "Arr"
        else:
            in_out = None
        return flight_no, in_out, carrier

    if normalized["flight_no"].notna().any():
        parsed = normalized["flight_no"].apply(split_flight_info)
        normalized["flight_no"] = parsed.map(lambda x: x[0])
        parsed_in_out = parsed.map(lambda x: x[1])
        parsed_carrier = parsed.map(lambda x: x[2])
        normalized["in_out"] = normalized["in_out"].where(
            normalized["in_out"].notna() & (normalized["in_out"].astype(str).str.strip() != ""),
            parsed_in_out,
        )
        normalized["airline_raw"] = normalized["airline_raw"].where(
            normalized["airline_raw"].notna() & (normalized["airline_raw"].astype(str).str.strip() != ""),
            parsed_carrier,
        )

    normalized["lead_bucket"] = normalized["lead_bucket"].map(
        lambda v: "planned" if v and "plan" in v else ("adhoc" if v and "ad" in v else None)
    )

    return normalized


def import_detail_report(path: str, session) -> int:
    existing = session.query(ImportFile).filter(ImportFile.source_file == path).first()
    if existing:
        session.query(PrmAnnouncement).filter(PrmAnnouncement.import_id == existing.id).delete()
        session.delete(existing)
        session.flush()

    df = load_detail_report(path)
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
        source_system="DPAX_DETAIL",
    )
    session.add(import_file)
    session.flush()

    def safe_str(value, max_len: int | None = None):
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if text.lower() == "nan" or text == "":
            return None
        if max_len is not None and len(text) > max_len:
            return text[:max_len]
        return text

    def normalize_airline_code(value) -> str | None:
        text = safe_str(value)
        if not text:
            return None
        if len(text) > 5:
            return None
        return text

    rows = []
    for _, row in df.iterrows():
        airline_raw = safe_str(row.get("airline_raw"), 255)
        airline_code = map_airline(airline_raw, session)
        flight_no = safe_str(row.get("flight_no"), 20)
        corrected_airline, corrected_flight_no = apply_flight_number_fix(
            airline_code or airline_raw,
            flight_no,
            session,
        )
        if corrected_airline:
            airline_code = map_airline(corrected_airline, session) or corrected_airline
        if corrected_flight_no:
            flight_no = corrected_flight_no
        airline_code = normalize_airline_code(airline_code)
        airport_code = map_destination(row.get("airport"), session)
        if not airport_code:
            airport_code = map_flight_destination(
                airline_code or airline_raw,
                flight_no,
                session,
            )

        rows.append(
            PrmAnnouncement(
                import_id=import_file.id,
                airline_code=airline_code,
                airline_raw=airline_raw,
                flight_no=flight_no,
                flight_date=row.get("flight_date"),
                lead_bucket=safe_str(row.get("lead_bucket"), 20),
                airport=None,
                airport_code=airport_code,
                wch_type=safe_str(row.get("wch_type"), 10),
                wch_category=map_wch_category(row.get("wch_type"), session),
                late_report=False,
                no_pax=False,
                in_out=safe_str(row.get("in_out"), 20),
            )
        )

    session.add_all(rows)
    return len(rows)
