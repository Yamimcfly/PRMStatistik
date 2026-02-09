import re
from pathlib import Path
from typing import Optional
import pandas as pd

from app.db.models import RefDestination


def _normalize_key(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    return text.upper()



def normalize_destination_key(value: str) -> str:
    return _normalize_key(value)


def load_destination_mapping(path: str, session) -> int:
    file_path = Path(path)
    if not file_path.exists():
        return 0

    try:
        df = pd.read_excel(file_path, sheet_name="Destinations")
    except Exception:
        df = pd.read_excel(file_path)

    if "IATA" not in df.columns or "Name" not in df.columns:
        return 0

    df = df[["IATA", "Name"]].dropna()

    entries = {}
    for _, row in df.iterrows():
        iata = str(row["IATA"]).strip().upper()
        name = str(row["Name"]).strip()
        if not iata or len(iata) != 3 or not name:
            continue
        iata_key = _normalize_key(iata)
        if iata_key and iata_key not in entries:
            entries[iata_key] = (iata, name)
        name_key = _normalize_key(name)
        if name_key and name_key not in entries:
            entries[name_key] = (iata, name)

    updated = 0
    for raw_value, (iata, name) in entries.items():
        session.merge(
            RefDestination(
                raw_value=raw_value,
                iata3=iata,
                display_name=name,
                mapping_source="auto",
            )
        )
        updated += 1
    return updated


def map_destination(raw_value: Optional[str], session) -> Optional[str]:
    if not raw_value:
        return None
    raw = str(raw_value).strip().upper()
    if not raw:
        return None

    if len(raw) == 3 and raw.isalpha():
        return raw

    code_match = re.search(r"(?<![A-Z])([A-Z]{3})(?![A-Z])", raw)
    if code_match:
        return code_match.group(1)

    key = _normalize_key(raw)
    mapped = session.get(RefDestination, key)
    if mapped and mapped.iata3:
        return mapped.iata3
    return None
