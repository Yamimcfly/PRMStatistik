from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base

class ImportFile(Base):
    __tablename__ = "import_files"
    id = Column(Integer, primary_key=True)
    source_file = Column(String(255), nullable=False)
    month_key = Column(String(7), nullable=False)  # YYYY-MM
    source_system = Column(String(50), nullable=False)  # ALT / FKB_NEW
    imported_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class PrmRequest(Base):
    __tablename__ = "prm_requests"
    request_id = Column(Integer, primary_key=True)  # from system
    operation_date = Column(DateTime, nullable=True)
    arr_con_dep = Column(String(20), nullable=True)
    ssr_code = Column(String(20), nullable=True)
    planned_adhoc = Column(String(50), nullable=True)
    call_status = Column(String(50), nullable=True)

    flight_number_raw = Column(String(50), nullable=True)  # e.g. 'D:TK 1672'
    carrier_iata2 = Column(String(3), nullable=True)
    flight_no = Column(String(10), nullable=True)

    bp_data_raw = Column(Text, nullable=True)
    bp_origin = Column(String(3), nullable=True)
    bp_destination = Column(String(3), nullable=True)

    airport_filled = Column(String(3), nullable=True)  # final Kap1 airport (may be NULL)
    import_id = Column(Integer, ForeignKey("import_files.id"), nullable=True)
    import_file = relationship("ImportFile")

class RefAirport(Base):
    __tablename__ = "ref_airport"
    iata = Column(String(3), primary_key=True)
    name = Column(String(255), nullable=True)
    mapping = Column(String(50), nullable=True)

class RefAirline(Base):
    __tablename__ = "ref_airline"
    iata2 = Column(String(3), primary_key=True)
    airline_name = Column(String(255), nullable=True)
    mapping = Column(String(50), nullable=True)


class RefAirlineMap(Base):
    __tablename__ = "ref_airline_map"
    raw_value = Column(String(100), primary_key=True)
    iata2 = Column(String(2), nullable=True)
    display_name = Column(String(255), nullable=True)
    mapping_source = Column(String(20), nullable=True)


class RefWchType(Base):
    __tablename__ = "ref_wch_type"
    raw_value = Column(String(50), primary_key=True)
    category_code = Column(String(10), nullable=True)
    category_name = Column(String(20), nullable=True)
    mapping_source = Column(String(20), nullable=True)


class RefDestination(Base):
    __tablename__ = "ref_destination"
    raw_value = Column(String(100), primary_key=True)
    iata3 = Column(String(3), nullable=True)
    display_name = Column(String(255), nullable=True)
    mapping_source = Column(String(20), nullable=True)


class RefFlightDestination(Base):
    __tablename__ = "ref_flight_destination"
    airline_key = Column(String(10), primary_key=True)
    flight_no_key = Column(String(20), primary_key=True)
    destination_iata3 = Column(String(3), nullable=True)
    display_name = Column(String(255), nullable=True)
    mapping_source = Column(String(20), nullable=True)


class RefFlightNumberFix(Base):
    __tablename__ = "ref_flight_number_fix"
    airline_key = Column(String(10), primary_key=True)
    flight_no_key = Column(String(20), primary_key=True)
    corrected_airline = Column(String(10), nullable=True)
    corrected_flight_no = Column(String(20), nullable=True)
    mapping_source = Column(String(20), nullable=True)


class PrmAnnouncement(Base):
    __tablename__ = "prm_announcements"
    id = Column(Integer, primary_key=True)
    import_id = Column(Integer, ForeignKey("import_files.id"), nullable=True)
    import_file = relationship("ImportFile")

    airline_code = Column(String(5), nullable=True)
    airline_raw = Column(String(255), nullable=True)
    handling_company = Column(String(255), nullable=True)
    flight_no = Column(String(20), nullable=True)
    flight_date = Column(Date, nullable=True)
    flight_time = Column(String(10), nullable=True)

    report_date = Column(Date, nullable=True)
    report_time = Column(String(10), nullable=True)
    lead_hours = Column(Float, nullable=True)
    lead_bucket = Column(String(20), nullable=True)  # adhoc/planned

    airport = Column(String(80), nullable=True)
    airport_code = Column(String(3), nullable=True)
    in_out = Column(String(20), nullable=True)
    wch_type = Column(String(10), nullable=True)
    wch_category = Column(String(20), nullable=True)
    late_report = Column(Boolean, default=False, nullable=False)
    no_pax = Column(Boolean, default=False, nullable=False)


class DpaxDailySummary(Base):
    __tablename__ = "dpax_daily_summary"
    id = Column(Integer, primary_key=True)
    import_id = Column(Integer, ForeignKey("import_files.id"), nullable=True)
    import_file = relationship("ImportFile")

    report_date = Column(Date, nullable=True)
    airline = Column(String(255), nullable=True)

    blnd = Column(Integer, nullable=True)
    deaf = Column(Integer, nullable=True)
    deafblnd = Column(Integer, nullable=True)
    dpax_noshow = Column(Integer, nullable=True)
    dpna = Column(Integer, nullable=True)
    maas = Column(Integer, nullable=True)
    meda = Column(Integer, nullable=True)
    preboard = Column(Integer, nullable=True)
    prebrdhs = Column(Integer, nullable=True)
    stcr = Column(Integer, nullable=True)
    wcbd = Column(Integer, nullable=True)
    wcbw = Column(Integer, nullable=True)
    wchc = Column(Integer, nullable=True)
    wchr = Column(Integer, nullable=True)
    wchs = Column(Integer, nullable=True)
    wcmp = Column(Integer, nullable=True)
    total_wch = Column(Integer, nullable=True)

    ad_hoc = Column(Integer, nullable=True)
    planned = Column(Integer, nullable=True)
    total_overall = Column(Integer, nullable=True)
