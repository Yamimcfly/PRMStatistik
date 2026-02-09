import pandas as pd
from sqlalchemy import func, case

from app.db.models import PrmAnnouncement, ImportFile

SSR_MAP = {
    "WCHR": "R",
    "WCHS": "S",
    "WCHC": "C",
    "WCMP": "C",
    "WCBD": "C",
    "WCBW": "C",
    "MAAS": "M",
    "MEDA": "M",
    "BLND": "B",
    "DEAF": "T",
    "DEAFBLND": "T",
    "STCR": "ST",
    "DPAX_NOSHOW": "NOSHOW",
    "DPNA": "DPNA",
}

EXCLUDE_SSR = set()  # Dpax NoShow und DPNA werden jetzt mitgezählt

def calculate_late_report_category(lead_hours, lead_bucket_str):
    """
    Berechnet Spätmeldungs-Kategorie:
    - Spätmeldung (<36h): lead_hours < 36 ODER lead_bucket = 'adhoc'
    - Keine Spätmeldung (>36h): lead_hours >= 36 ODER lead_bucket = 'planned'
    """
    # Priorität 1: lead_hours falls vorhanden
    if lead_hours is not None:
        return "<36h" if lead_hours < 36 else ">36h"
    
    # Priorität 2: lead_bucket String
    if lead_bucket_str:
        s = str(lead_bucket_str).strip().lower()
        if "plan" in s:
            return ">36h"
        if "adhoc" in s or "ad-hoc" in s or "ad hoc" in s:
            return "<36h"
    
    return None

def lead_bucket(planned_adhoc: str | None):
    """Legacy Funktion für Kompatibilität - nutzt nur den String"""
    return calculate_late_report_category(None, planned_adhoc)

def compute_kap1_kap2_kap3(detail_df: pd.DataFrame):
    """Return (kap1, kap2, kap3_summary, kap3_detail). Expects normalized columns."""
    df = detail_df.copy()
    df["kap3_cat"] = df["ssr_code"].map(SSR_MAP)
    df = df[df["ssr_code"].notna() & ~df["ssr_code"].isin(EXCLUDE_SSR) & df["kap3_cat"].notna()].copy()
    df["lead_bucket"] = df.apply(lambda row: calculate_late_report_category(row.get("lead_hours"), row.get("planned_adhoc")), axis=1)
    cat_cols = ["R","S","C","M","B","T","ST","NOSHOW","DPNA"]

    # Kap1
    k1 = (df.pivot_table(index="airport_filled", columns="kap3_cat", values="request_id", aggfunc="count", fill_value=0)
            .reindex(columns=cat_cols, fill_value=0))
    k1_lead = (df.pivot_table(index="airport_filled", columns="lead_bucket", values="request_id", aggfunc="count", fill_value=0)
                 .reindex(columns=[">36h","<36h"], fill_value=0))
    kap1 = k1.join(k1_lead).reset_index().rename(columns={"airport_filled":"Destination_Key"})
    kap1["Gesamt_Pax"] = kap1[cat_cols].sum(axis=1).astype(int)
    kap1 = kap1.sort_values("Gesamt_Pax", ascending=False)

    # Kap2
    k2 = (df.pivot_table(index="carrier_iata2", columns="kap3_cat", values="request_id", aggfunc="count", fill_value=0)
            .reindex(columns=cat_cols, fill_value=0))
    k2_lead = (df.pivot_table(index="carrier_iata2", columns="lead_bucket", values="request_id", aggfunc="count", fill_value=0)
                 .reindex(columns=[">36h","<36h"], fill_value=0))
    kap2 = k2.join(k2_lead).reset_index().rename(columns={"carrier_iata2":"Airline_Key"})
    kap2["Gesamt_Pax"] = kap2[cat_cols].sum(axis=1).astype(int)
    kap2 = kap2.sort_values("Gesamt_Pax", ascending=False)

    # Kap3 detail + summary
    kap3_detail = (df.groupby("kap3_cat")["request_id"].count().reindex(cat_cols, fill_value=0).reset_index()
                   .rename(columns={"kap3_cat":"WCH_Kategorie", "request_id":"Gesamt_Pax"}))
    lead = (df.pivot_table(index="kap3_cat", columns="lead_bucket", values="request_id", aggfunc="count", fill_value=0)
              .reindex(index=cat_cols, columns=[">36h","<36h"], fill_value=0).reset_index()
              .rename(columns={"kap3_cat":"WCH_Kategorie"}))
    kap3_detail = kap3_detail.merge(lead, on="WCH_Kategorie", how="left")

    summary = {c:int(kap3_detail.loc[kap3_detail["WCH_Kategorie"]==c,"Gesamt_Pax"].iloc[0]) for c in cat_cols}
    summary["Gesamt_Pax"] = int(sum(summary[c] for c in cat_cols))
    summary[">36h"] = int((df["lead_bucket"]==">36h").sum())
    summary["<36h"] = int((df["lead_bucket"]=="<36h").sum())
    kap3_summary = pd.DataFrame([summary])[cat_cols+["Gesamt_Pax",">36h","<36h"]]

    return kap1, kap2, kap3_summary, kap3_detail


def _apply_filters(query, month_key, in_out, airline, wch_category):
    if month_key:
        query = query.filter(ImportFile.month_key == month_key)
    if in_out:
        query = query.filter(PrmAnnouncement.in_out == in_out)
    if airline:
        query = query.filter(PrmAnnouncement.airline_code == airline)
    if wch_category:
        query = query.filter(PrmAnnouncement.wch_category == wch_category)
    return query


def get_filter_options(session) -> dict:
    months = [r[0] for r in session.query(ImportFile.month_key).distinct().order_by(ImportFile.month_key).all()]
    in_out = [r[0] for r in session.query(PrmAnnouncement.in_out).distinct().order_by(PrmAnnouncement.in_out).all() if r[0]]
    airlines = [r[0] for r in session.query(PrmAnnouncement.airline_code).distinct().order_by(PrmAnnouncement.airline_code).all() if r[0]]
    wch_types = [r[0] for r in session.query(PrmAnnouncement.wch_category).distinct().order_by(PrmAnnouncement.wch_category).all() if r[0]]
    return {
        "months": months,
        "in_out": in_out,
        "airlines": airlines,
        "wch_types": wch_types,
    }


def compute_destination_stats(session, month_key=None, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    # SQL CASE-Ausdruck für Spätmeldungs-Kategorie
    late_category = case(
        (PrmAnnouncement.lead_hours < 36, "<36h"),
        (PrmAnnouncement.lead_hours >= 36, ">36h"),
        (PrmAnnouncement.lead_bucket.like("%plan%"), ">36h"),
        (PrmAnnouncement.lead_bucket.like("%adhoc%"), "<36h"),
        (PrmAnnouncement.lead_bucket.like("%ad-hoc%"), "<36h"),
        else_=None
    ).label("LeadBucket")
    
    base = (
        session.query(
            PrmAnnouncement.airport_code.label("AirportCode"),
            PrmAnnouncement.airport.label("AirportRaw"),
            PrmAnnouncement.wch_category.label("WCH_Category"),
            late_category,
        )
        .join(ImportFile, ImportFile.id == PrmAnnouncement.import_id, isouter=True)
        .filter(PrmAnnouncement.wch_category.isnot(None))
    )
    base = _apply_filters(base, month_key, in_out, airline, wch_category)
    df = pd.DataFrame(base.all(), columns=["AirportCode", "AirportRaw", "WCH_Category", "LeadBucket"])
    if df.empty:
        return df

    df["Destination"] = df["AirportCode"].fillna(df["AirportRaw"]).fillna("OHNE ZIEL")

    categories = ["WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS", "STRETCHER", "DPAX_NOSHOW", "DPNA"]
    index_cols = ["Destination"]

    total_cat = df.groupby(index_cols + ["WCH_Category"]).size().unstack(fill_value=0)
    late_total = df[df["LeadBucket"] == "<36h"].groupby(index_cols).size()
    ontime_total = df[df["LeadBucket"] == ">36h"].groupby(index_cols).size()

    for cat in categories:
        if cat not in total_cat.columns:
            total_cat[cat] = 0

    total_cat = total_cat[categories]

    result = total_cat.add_prefix("Total_")
    result["<36h"] = late_total
    result[">36h"] = ontime_total
    result["Gesamt_PRM"] = total_cat.sum(axis=1)
    result = result.reset_index()
    return result


def compute_airline_stats(session, month_key=None, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    # SQL CASE-Ausdruck für Spätmeldungs-Kategorie
    late_category = case(
        (PrmAnnouncement.lead_hours < 36, "<36h"),
        (PrmAnnouncement.lead_hours >= 36, ">36h"),
        (PrmAnnouncement.lead_bucket.like("%plan%"), ">36h"),
        (PrmAnnouncement.lead_bucket.like("%adhoc%"), "<36h"),
        (PrmAnnouncement.lead_bucket.like("%ad-hoc%"), "<36h"),
        else_=None
    ).label("LeadBucket")
    
    base = (
        session.query(
            PrmAnnouncement.airline_code.label("Airline"),
            PrmAnnouncement.wch_category.label("WCH_Category"),
            late_category,
        )
        .join(ImportFile, ImportFile.id == PrmAnnouncement.import_id, isouter=True)
        .filter(PrmAnnouncement.wch_category.isnot(None))
    )
    base = _apply_filters(base, month_key, in_out, airline, wch_category)
    df = pd.DataFrame(base.all(), columns=["Airline", "WCH_Category", "LeadBucket"])
    if df.empty:
        return df

    df["Airline"] = df["Airline"].fillna("OHNE AIRLINE")

    categories = ["WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS", "STRETCHER", "DPAX_NOSHOW", "DPNA"]
    index_cols = ["Airline"]

    total_cat = df.groupby(index_cols + ["WCH_Category"]).size().unstack(fill_value=0)
    late_total = df[df["LeadBucket"] == "<36h"].groupby(index_cols).size()
    ontime_total = df[df["LeadBucket"] == ">36h"].groupby(index_cols).size()

    for cat in categories:
        if cat not in total_cat.columns:
            total_cat[cat] = 0

    total_cat = total_cat[categories]

    result = total_cat.add_prefix("Total_")
    result["<36h"] = late_total
    result[">36h"] = ontime_total
    result["Gesamt_PRM"] = total_cat.sum(axis=1)
    result = result.reset_index()
    return result


def _quarter_from_month(month_key: str) -> str | None:
    if not month_key or len(month_key) < 7:
        return None
    try:
        year = month_key[:4]
        month = int(month_key[5:7])
    except Exception:
        return None
    quarter = (month - 1) // 3 + 1
    return f"{year}-Q{quarter}"


def _monthly_base(session, in_out=None, airline=None, wch_category=None):
    # SQL CASE-Ausdruck für Spätmeldungs-Kategorie
    late_category = case(
        (PrmAnnouncement.lead_hours < 36, "<36h"),
        (PrmAnnouncement.lead_hours >= 36, ">36h"),
        (PrmAnnouncement.lead_bucket.like("%plan%"), ">36h"),
        (PrmAnnouncement.lead_bucket.like("%adhoc%"), "<36h"),
        (PrmAnnouncement.lead_bucket.like("%ad-hoc%"), "<36h"),
        else_=None
    ).label("LeadBucket")
    
    base = (
        session.query(
            ImportFile.month_key.label("Month"),
            PrmAnnouncement.airport_code.label("AirportCode"),
            PrmAnnouncement.airport.label("AirportRaw"),
            PrmAnnouncement.airline_code.label("Airline"),
            PrmAnnouncement.wch_category.label("WCH_Category"),
            late_category,
        )
        .join(ImportFile, ImportFile.id == PrmAnnouncement.import_id, isouter=True)
        .filter(PrmAnnouncement.wch_category.isnot(None))
    )
    return _apply_filters(base, None, in_out, airline, wch_category)


def compute_monthly_destination_stats(session, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    base = _monthly_base(session, in_out, airline, wch_category)
    df = pd.DataFrame(
        base.all(),
        columns=["Month", "AirportCode", "AirportRaw", "Airline", "WCH_Category", "LeadBucket"],
    )
    if df.empty:
        return df

    df["Destination"] = df["AirportCode"].fillna(df["AirportRaw"]).fillna("OHNE ZIEL")

    categories = ["WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS", "STRETCHER", "DPAX_NOSHOW", "DPNA"]
    index_cols = ["Month", "Destination"]

    total_cat = df.groupby(index_cols + ["WCH_Category"]).size().unstack(fill_value=0)
    for cat in categories:
        if cat not in total_cat.columns:
            total_cat[cat] = 0

    total_cat = total_cat[categories]
    late_total = df[df["LeadBucket"] == "<36h"].groupby(index_cols).size()
    ontime_total = df[df["LeadBucket"] == ">36h"].groupby(index_cols).size()

    result = total_cat.add_prefix("Total_")
    result["<36h"] = late_total
    result[">36h"] = ontime_total
    result["Gesamt_PRM"] = total_cat.sum(axis=1)
    result = result.reset_index().sort_values(by=["Month", "Destination"])
    return result


def compute_monthly_airline_stats(session, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    base = _monthly_base(session, in_out, airline, wch_category)
    df = pd.DataFrame(
        base.all(),
        columns=["Month", "AirportCode", "AirportRaw", "Airline", "WCH_Category", "LeadBucket"],
    )
    if df.empty:
        return df

    df["Airline"] = df["Airline"].fillna("OHNE AIRLINE")

    categories = ["WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS", "STRETCHER", "DPAX_NOSHOW", "DPNA"]
    index_cols = ["Month", "Airline"]

    total_cat = df.groupby(index_cols + ["WCH_Category"]).size().unstack(fill_value=0)
    for cat in categories:
        if cat not in total_cat.columns:
            total_cat[cat] = 0

    total_cat = total_cat[categories]
    late_total = df[df["LeadBucket"] == "<36h"].groupby(index_cols).size()
    ontime_total = df[df["LeadBucket"] == ">36h"].groupby(index_cols).size()

    result = total_cat.add_prefix("Total_")
    result["<36h"] = late_total
    result[">36h"] = ontime_total
    result["Gesamt_PRM"] = total_cat.sum(axis=1)
    result = result.reset_index().sort_values(by=["Month", "Airline"])
    return result


def compute_quarterly_destination_stats(session, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    monthly = compute_monthly_destination_stats(session, in_out, airline, wch_category)
    if monthly.empty:
        return monthly
    monthly["Quarter"] = monthly["Month"].apply(_quarter_from_month)
    group_cols = ["Quarter", "Destination"]
    agg_cols = [c for c in monthly.columns if c.startswith("Total_") or c in ["Spaetmeldungen", "Gesamt_PRM"]]
    result = monthly.groupby(group_cols)[agg_cols].sum().reset_index().sort_values(group_cols)
    return result


def compute_quarterly_airline_stats(session, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    monthly = compute_monthly_airline_stats(session, in_out, airline, wch_category)
    if monthly.empty:
        return monthly
    monthly["Quarter"] = monthly["Month"].apply(_quarter_from_month)
    group_cols = ["Quarter", "Airline"]
    agg_cols = [c for c in monthly.columns if c.startswith("Total_") or c in ["Spaetmeldungen", "Gesamt_PRM"]]
    result = monthly.groupby(group_cols)[agg_cols].sum().reset_index().sort_values(group_cols)
    return result


def compute_monthly_summary_stats(session, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    base = _monthly_base(session, in_out, airline, wch_category)
    df = pd.DataFrame(
        base.all(),
        columns=["Month", "AirportCode", "AirportRaw", "Airline", "WCH_Category", "LeadBucket"],
    )
    if df.empty:
        return df

    categories = ["WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS", "STRETCHER", "DPAX_NOSHOW", "DPNA"]
    index_cols = ["Month"]

    total_cat = df.groupby(index_cols + ["WCH_Category"]).size().unstack(fill_value=0)
    for cat in categories:
        if cat not in total_cat.columns:
            total_cat[cat] = 0

    total_cat = total_cat[categories]
    late_total = df[df["LeadBucket"] == "<36h"].groupby(index_cols).size()
    ontime_total = df[df["LeadBucket"] == ">36h"].groupby(index_cols).size()

    result = total_cat.add_prefix("Total_")
    result["<36h"] = late_total
    result[">36h"] = ontime_total
    result["Gesamt_WCH"] = total_cat.sum(axis=1)
    result["Spaetmeldungen_Prozent"] = (
        (result["<36h"] / result["Gesamt_WCH"]) * 100
    ).fillna(0).round(2)
    result = result.reset_index().sort_values(by=["Month"])
    return result


def compute_daily_stats(session, month_key=None, in_out=None, airline=None, wch_category=None) -> pd.DataFrame:
    """Tägliche Statistik für einen ausgewählten Monat"""
    # SQL CASE-Ausdruck für Spätmeldungs-Kategorie
    late_category = case(
        (PrmAnnouncement.lead_hours < 36, "<36h"),
        (PrmAnnouncement.lead_hours >= 36, ">36h"),
        (PrmAnnouncement.lead_bucket.like("%plan%"), ">36h"),
        (PrmAnnouncement.lead_bucket.like("%adhoc%"), "<36h"),
        (PrmAnnouncement.lead_bucket.like("%ad-hoc%"), "<36h"),
        else_=None
    ).label("LeadBucket")
    
    base = (
        session.query(
            PrmAnnouncement.flight_date.label("Datum"),
            PrmAnnouncement.wch_category.label("WCH_Category"),
            late_category,
        )
        .join(ImportFile, ImportFile.id == PrmAnnouncement.import_id, isouter=True)
        .filter(PrmAnnouncement.wch_category.isnot(None))
        .filter(PrmAnnouncement.flight_date.isnot(None))
    )
    base = _apply_filters(base, month_key, in_out, airline, wch_category)
    
    df = pd.DataFrame(base.all(), columns=["Datum", "WCH_Category", "LeadBucket"])
    if df.empty:
        return df

    categories = ["WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS", "STRETCHER", "DPAX_NOSHOW", "DPNA"]
    index_cols = ["Datum"]

    total_cat = df.groupby(index_cols + ["WCH_Category"]).size().unstack(fill_value=0)
    for cat in categories:
        if cat not in total_cat.columns:
            total_cat[cat] = 0

    total_cat = total_cat[categories]
    late_total = df[df["LeadBucket"] == "<36h"].groupby(index_cols).size()
    ontime_total = df[df["LeadBucket"] == ">36h"].groupby(index_cols).size()

    result = total_cat.add_prefix("Total_")
    result["<36h"] = late_total
    result[">36h"] = ontime_total
    result["Gesamt_PRM"] = total_cat.sum(axis=1)
    result = result.reset_index().sort_values(by=["Datum"])
    
    # Formatiere Datum als String
    result["Datum"] = pd.to_datetime(result["Datum"]).dt.strftime("%Y-%m-%d")
    
    return result


def fetch_import_history(session) -> pd.DataFrame:
    rows = (
        session.query(
            ImportFile.imported_at.label("Imported_At"),
            ImportFile.source_system.label("Source"),
            ImportFile.month_key.label("Month"),
            ImportFile.source_file.label("Source_File"),
        )
        .order_by(ImportFile.imported_at.desc())
        .all()
    )
    return pd.DataFrame(rows, columns=["Imported_At", "Source", "Month", "Source_File"])
