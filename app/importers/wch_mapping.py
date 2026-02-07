import re
from pathlib import Path
from typing import Optional
import pandas as pd

from app.db.models import RefWchType

CATEGORY_MAP = {
    "R": "WCHR",
    "S": "WCHS",
    "C": "WCHC",
    "B": "BLIND",
    "T": "TAUB",
    "M": "MAAS",
    "ST": "STRETCHER",
    "STRETCHER": "STRETCHER",
}

PRIORITY = ["WCHC", "WCHS", "WCHR", "STRETCHER", "MAAS", "BLIND", "TAUB"]


def _normalize_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().strip())


def _normalize_category(code: str) -> Optional[str]:
    if not code:
        return None
    key = _normalize_token(code)
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    return None


def load_wch_mapping(path: str, session) -> int:
    file_path = Path(path)
    if not file_path.exists():
        return 0

    try:
        df = pd.read_excel(file_path, sheet_name="WCH Kat")
    except Exception:
        df = pd.read_excel(file_path)

    if "IATA" not in df.columns or "Name" not in df.columns:
        return 0

    df = df[["IATA", "Name"]].dropna()
    mapping = {}
    for _, row in df.iterrows():
        raw = str(row["IATA"]).strip()
        if not raw:
            continue
        code = str(row["Name"]).strip()
        category = _normalize_category(code)
        if category is None:
            continue
        tokens = [t.strip() for t in raw.split(",") if t.strip()]
        for token in tokens:
            key = _normalize_token(token)
            if not key:
                continue
            mapping[key] = (code, category)

    updated = 0
    for key, (code, category) in mapping.items():
        session.merge(RefWchType(raw_value=key, category_code=code, category_name=category))
        updated += 1
    return updated


def map_wch_category(raw_value: Optional[str], session) -> Optional[str]:
    if not raw_value:
        return None
    raw = str(raw_value).strip().upper()
    if not raw:
        return None

    # direct keyword shortcuts
    if "STRE" in raw or "STCR" in raw:
        return "STRETCHER"
    if "WCHC" in raw:
        return "WCHC"
    if "WCHS" in raw:
        return "WCHS"
    if "WCHR" in raw:
        return "WCHR"
    if "MAAS" in raw:
        return "MAAS"
    if "BLND" in raw or "BLIND" in raw:
        return "BLIND"
    if "DEAF" in raw or "TAUB" in raw:
        return "TAUB"

    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    categories = []
    for token in tokens:
        key = _normalize_token(token)
        if not key:
            continue
        mapped = session.get(RefWchType, key)
        if mapped and mapped.category_name:
            categories.append(mapped.category_name)

    for cat in PRIORITY:
        if cat in categories:
            return cat
    return categories[0] if categories else None
