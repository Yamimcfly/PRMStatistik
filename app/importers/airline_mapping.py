import json
import re
from pathlib import Path
from typing import Optional

from app.db.models import RefAirlineMap


def _normalize_key(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    return text.upper()


def normalize_airline_key(value: str) -> str:
    return _normalize_key(value)


def load_airline_mapping(path: str, session) -> int:
    file_path = Path(path)
    if not file_path.exists():
        return 0

    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return 0

    entries = {}
    for code, name in data.items():
        if code is None:
            continue
        code_str = str(code).strip().upper()
        name_str = str(name).strip() if name is not None else ""
        if len(code_str) != 2:
            continue
        code_key = _normalize_key(code_str)
        if code_key and code_key not in entries:
            entries[code_key] = (code_str, name_str)
        if name_str:
            name_key = _normalize_key(name_str)
            if name_key and name_key not in entries:
                entries[name_key] = (code_str, name_str)

    updated = 0
    for raw_value, (iata2, display_name) in entries.items():
        session.merge(
            RefAirlineMap(
                raw_value=raw_value,
                iata2=iata2,
                display_name=display_name,
                mapping_source="auto",
            )
        )
        updated += 1
    return updated


def map_airline(raw_value: Optional[str], session) -> Optional[str]:
    if not raw_value:
        return None
    raw = str(raw_value).strip().upper()
    if not raw:
        return None

    if len(raw) == 2 and raw.isalnum():
        return raw

    code_match = re.search(r"(?<![A-Z0-9])([A-Z0-9]{2})(?![A-Z0-9])", raw)
    if code_match:
        return code_match.group(1)

    key = _normalize_key(raw)
    mapped = session.get(RefAirlineMap, key)
    if mapped and mapped.iata2:
        return mapped.iata2
    return None
