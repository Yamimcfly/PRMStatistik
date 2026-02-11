import re
from typing import Tuple, Optional

def parse_flight_number(raw: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse 'D:TK 1672' or 'TK 1672' -> (dir, carrier, flight_no)
    dir is 'D'/'A' if present.
    """
    if not raw:
        return None, None, None
    s = raw.strip().upper()
    m = re.search(r"([AD]):\s*([A-Z0-9]{2,3})\s*0*([0-9]{1,5})", s)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = re.search(r"\b([A-Z0-9]{2,3})\s*0*([0-9]{1,5})\b", s)
    if m:
        return None, m.group(1), m.group(2)
    return None, None, None

def parse_bp_origin_dest(bp_raw: Optional[str], station_iata: str, arr_con_dep: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Heuristic BCBP parsing around station (e.g., CGN). Returns (origin, destination) if found.
    """
    if not bp_raw or len(bp_raw) < 10:
        return None, None
    s = bp_raw.strip().upper()
    station = (station_iata or "").upper()
    p = s.find(station)
    if p == -1:
        return None, None

    before = s[max(0, p-3):p]
    after = s[p+3:p+6]

    def is_airport(x: str) -> bool:
        return bool(re.fullmatch(r"[A-Z]{3}", x or ""))

    acd = (arr_con_dep or "").lower()
    if "dep" in acd and is_airport(after):
        return station, after
    if "arr" in acd and is_airport(before):
        return before, station

    if is_airport(after):
        return station, after
    if is_airport(before):
        return before, station
    return None, None
