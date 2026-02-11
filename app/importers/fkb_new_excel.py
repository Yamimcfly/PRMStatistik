import pandas as pd
from typing import Tuple
from app.services.parsing import parse_flight_number, parse_bp_origin_dest
from app.config import STATION_IATA

def load_fkb_new_detail(path: str) -> pd.DataFrame:
    """Load the 'Passenger Detail' block from the combined export and normalize columns."""
    raw = pd.read_excel(path, sheet_name=0, header=None, engine="openpyxl")
    header_row = None
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).tolist()
        if "Operation Date" in row and "Request ID" in row:
            header_row = i
            break
    if header_row is None:
        raise ValueError("Detail header row not found (Operation Date / Request ID).")
    df = pd.read_excel(path, sheet_name=0, header=header_row, engine="openpyxl")
    df = df.dropna(axis=1, how="all")
    df = df.loc[:, [c for c in df.columns if not (isinstance(c, str) and c.startswith("Unnamed"))]]
    df.columns = [str(c).strip() for c in df.columns]
    df = df[df["Request ID"].notna()].copy()

    # Normalize
    df["Operation Date"] = pd.to_datetime(df["Operation Date"], errors="coerce")
    df["Request ID"] = pd.to_numeric(df["Request ID"], errors="coerce").astype("Int64")
    df["SSR Code"] = df.get("SSR Code")
    df["Planned / Adhoc"] = df.get("Planned / Adhoc")
    df["Call Status"] = df.get("Call Status")
    df["Arr/Con/Dep"] = df.get("Arr/Con/Dep")

    # Flight parse
    dir_, carrier, flt = zip(*df.get("Flight Number", pd.Series([None]*len(df))).map(parse_flight_number))
    df["carrier_iata2"] = carrier
    df["flight_no"] = flt

    # bp parse
    bp = df.get("bp Data Raw")
    if bp is not None:
        od = df.apply(lambda r: parse_bp_origin_dest(r.get("bp Data Raw"), STATION_IATA, r.get("Arr/Con/Dep")), axis=1, result_type="expand")
        od.columns = ["bp_origin", "bp_destination"]
        df = pd.concat([df, od], axis=1)
    else:
        df["bp_origin"] = None
        df["bp_destination"] = None

    # airport_filled: prefer outbound destination / inbound origin
    def pick_airport(r):
        acd = str(r.get("Arr/Con/Dep","")).lower()
        if "dep" in acd:
            return r.get("bp_destination")
        if "arr" in acd:
            return r.get("bp_origin")
        return r.get("bp_destination") or r.get("bp_origin")

    df["airport_filled"] = df.apply(pick_airport, axis=1)

    # Return only normalized columns
    out = pd.DataFrame({
        "request_id": df["Request ID"].astype("Int64"),
        "operation_date": df["Operation Date"],
        "arr_con_dep": df["Arr/Con/Dep"],
        "ssr_code": df["SSR Code"],
        "planned_adhoc": df["Planned / Adhoc"],
        "call_status": df["Call Status"],
        "flight_number_raw": df.get("Flight Number"),
        "carrier_iata2": df["carrier_iata2"],
        "flight_no": df["flight_no"],
        "bp_data_raw": df.get("bp Data Raw"),
        "bp_origin": df.get("bp_origin"),
        "bp_destination": df.get("bp_destination"),
        "airport_filled": df.get("airport_filled"),
    })
    return out
