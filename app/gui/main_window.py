from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QLabel, QHBoxLayout, QTableWidget, QTableWidgetItem, QTabWidget, QMessageBox,
    QComboBox, QDialog, QHeaderView, QAbstractItemView, QFormLayout, QLineEdit,
    QDialogButtonBox
)
from PySide6.QtCore import Qt
from sqlalchemy import or_
import os
import re
import sys
import pandas as pd

from app.config import (
    IMPORT_DIR,
    EXPORT_DIR,
    GUI_SETTINGS,
    FILTER_DEFAULTS,
    WCH_MAPPING_FILE,
    DESTINATION_MAPPING_FILE,
    AIRLINE_MAPPING_FILE,
)
from app.db.session import init_db, SessionLocal
from app.importers.voranmeldungen_excel import can_handle as can_handle_voranmeldungen
from app.importers.voranmeldungen_excel import import_voranmeldungen
from app.importers.dpax_summary_excel import can_handle as can_handle_dpax
from app.importers.dpax_summary_excel import import_dpax_summary
from app.importers.dpax_passenger_detail_excel import (
    can_handle as can_handle_detail,
    import_detail_report,
)
from app.services.statistics import (
    compute_destination_stats,
    compute_airline_stats,
    compute_monthly_destination_stats,
    compute_monthly_airline_stats,
    compute_quarterly_destination_stats,
    compute_quarterly_airline_stats,
    compute_monthly_summary_stats,
    get_filter_options,
    fetch_import_history,
)
from app.importers.wch_mapping import load_wch_mapping, map_wch_category, CATEGORY_MAP
from app.importers.destination_mapping import (
    load_destination_mapping,
    map_destination,
    normalize_destination_key,
)
from app.importers.airline_mapping import (
    load_airline_mapping,
    map_airline,
    normalize_airline_key,
)
from app.importers.flight_destination_mapping import (
    map_flight_destination,
    normalize_flight_no,
)
from app.db.models import (
    RefWchType,
    PrmAnnouncement,
    ImportFile,
    DpaxDailySummary,
    RefDestination,
    RefAirlineMap,
    RefFlightDestination,
    RefFlightNumberFix,
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FKB PRM Statistik – Prototype")
        width = int(GUI_SETTINGS.get("width", 1100))
        height = int(GUI_SETTINGS.get("height", 700))
        self.resize(width, height)

        init_db()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Controls
        row = QHBoxLayout()
        self.lbl = QLabel("Excel-Dateien importieren und Statistiken anzeigen.")
        btn_pick = QPushButton("Excel importieren…")
        btn_pick.clicked.connect(self.import_files)
        btn_refresh = QPushButton("Statistik aktualisieren")
        btn_refresh.clicked.connect(self.refresh_stats)
        btn_export = QPushButton("Export aktuelle Tabelle…")
        btn_export.clicked.connect(self.export_current_tab)
        btn_export_super = QPushButton("Super Export…")
        btn_export_super.clicked.connect(self.export_super)
        row.addWidget(self.lbl)
        row.addStretch(1)
        row.addWidget(btn_pick)
        row.addWidget(btn_refresh)
        row.addWidget(btn_export)
        row.addWidget(btn_export_super)
        layout.addLayout(row)

        row_actions = QHBoxLayout()
        btn_wch = QPushButton("WCH Mapping bearbeiten…")
        btn_wch.clicked.connect(self.edit_wch_mapping)
        btn_dest = QPushButton("Destination Mapping bearbeiten…")
        btn_dest.clicked.connect(self.edit_destination_mapping)
        btn_airline = QPushButton("Airline Mapping bearbeiten…")
        btn_airline.clicked.connect(self.edit_airline_mapping)
        btn_flight = QPushButton("Flugnummer Mapping bearbeiten…")
        btn_flight.clicked.connect(self.edit_flight_mapping)
        btn_delete_import = QPushButton("Import loeschen")
        btn_delete_import.clicked.connect(self.delete_selected_import)
        row_actions.addWidget(btn_wch)
        row_actions.addWidget(btn_dest)
        row_actions.addWidget(btn_airline)
        row_actions.addWidget(btn_flight)
        row_actions.addWidget(btn_delete_import)
        row_actions.addStretch(1)
        layout.addLayout(row_actions)

        row_status = QHBoxLayout()
        row_status.addWidget(QLabel("Mapping-Status:"))
        self.lbl_wch_status = QLabel("")
        self.lbl_dest_status = QLabel("")
        self.lbl_airline_status = QLabel("")
        self.lbl_flight_status = QLabel("")
        row_status.addWidget(self.lbl_wch_status)
        row_status.addWidget(self.lbl_dest_status)
        row_status.addWidget(self.lbl_airline_status)
        row_status.addWidget(self.lbl_flight_status)
        row_status.addStretch(1)
        layout.addLayout(row_status)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Monat"))
        self.cmb_month = QComboBox()
        self.cmb_month.currentIndexChanged.connect(self.refresh_stats)
        filter_row.addWidget(self.cmb_month)

        filter_row.addWidget(QLabel("In/Out"))
        self.cmb_inout = QComboBox()
        self.cmb_inout.currentIndexChanged.connect(self.refresh_stats)
        filter_row.addWidget(self.cmb_inout)

        filter_row.addWidget(QLabel("Airline"))
        self.cmb_airline = QComboBox()
        self.cmb_airline.currentIndexChanged.connect(self.refresh_stats)
        filter_row.addWidget(self.cmb_airline)

        filter_row.addWidget(QLabel("WCH"))
        self.cmb_wch = QComboBox()
        self.cmb_wch.currentIndexChanged.connect(self.refresh_stats)
        filter_row.addWidget(self.cmb_wch)

        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tab_dest = QTableWidget()
        self.tab_airline = QTableWidget()
        self.tab_history = QTableWidget()
        self.tabs.addTab(self.tab_dest, "Destinationen + WCH")
        self.tabs.addTab(self.tab_airline, "Airlines + WCH")
        self.tabs.addTab(self.tab_history, "Import-Historie")

        self.last_data = {}
        self._defaults_applied = False
        self.refresh_filters()
        self.refresh_stats()

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Excel auswählen",
            str(IMPORT_DIR),
            "Excel (*.xlsx *.xls)",
        )
        if not paths:
            return

        imported = 0
        skipped = []
        session = SessionLocal()
        try:
            if WCH_MAPPING_FILE:
                load_wch_mapping(WCH_MAPPING_FILE, session)
            if DESTINATION_MAPPING_FILE:
                load_destination_mapping(DESTINATION_MAPPING_FILE, session)
            if AIRLINE_MAPPING_FILE:
                load_airline_mapping(AIRLINE_MAPPING_FILE, session)
            for path in paths:
                if can_handle_voranmeldungen(path):
                    imported += import_voranmeldungen(path, session)
                elif can_handle_detail(path):
                    imported += import_detail_report(path, session)
                elif can_handle_dpax(path):
                    imported += import_dpax_summary(path, session)
                else:
                    skipped.append(path)
            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        self.refresh_filters()
        self.refresh_stats()
        message = f"Importiert: {imported} Datensaetze"
        if skipped:
            message += f" | Uebersprungen: {len(skipped)}"
        self.lbl.setText(message)

    def refresh_stats(self):
        session = SessionLocal()
        try:
            month = self._current_value(self.cmb_month)
            in_out = self._current_value(self.cmb_inout)
            airline = self._current_value(self.cmb_airline)
            wch_type = self._current_value(self.cmb_wch)

            dest = compute_destination_stats(session, month, in_out, airline, wch_type)
            airline_df = compute_airline_stats(session, month, in_out, airline, wch_type)
            history_df = fetch_import_history(session)
            self.show_df(self.tab_dest, dest)
            self.show_df(self.tab_airline, airline_df)
            self.show_df(self.tab_history, history_df)
            self.last_data = {
                "Destinationen + WCH": dest,
                "Airlines + WCH": airline_df,
                "Import-Historie": history_df,
            }
        finally:
            session.close()
        self.update_mapping_status()

    def refresh_filters(self):
        session = SessionLocal()
        try:
            options = get_filter_options(session)
        finally:
            session.close()

        self._set_combo_values(self.cmb_month, options.get("months", []))
        self._set_combo_values(self.cmb_inout, options.get("in_out", []))
        self._set_combo_values(self.cmb_airline, options.get("airlines", []))
        self._set_combo_values(self.cmb_wch, options.get("wch_types", []))

        if not self._defaults_applied:
            self._apply_filter_defaults()
            self._defaults_applied = True

    def export_current_tab(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        df = self.last_data.get(tab_name)
        if df is None or df.empty:
            QMessageBox.information(self, "Hinweis", "Keine Daten zum Export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export",
            str(EXPORT_DIR),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            df.to_excel(path, index=False)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))

    def export_super(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Super Export",
            str(EXPORT_DIR),
            "Excel (*.xlsx)",
        )
        if not path:
            return

        session = SessionLocal()
        try:
            in_out = self._current_value(self.cmb_inout)
            airline = self._current_value(self.cmb_airline)
            wch_type = self._current_value(self.cmb_wch)

            dest_month = compute_monthly_destination_stats(session, in_out, airline, wch_type)
            airline_month = compute_monthly_airline_stats(session, in_out, airline, wch_type)
            dest_quarter = compute_quarterly_destination_stats(session, in_out, airline, wch_type)
            airline_quarter = compute_quarterly_airline_stats(session, in_out, airline, wch_type)
            summary_month = compute_monthly_summary_stats(session, in_out, airline, wch_type)
            history_df = fetch_import_history(session)

            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                dest_month.to_excel(writer, sheet_name="Monat_Destination", index=False)
                airline_month.to_excel(writer, sheet_name="Monat_Airline", index=False)
                summary_month.to_excel(writer, sheet_name="Monat_Gesamt", index=False)
                dest_quarter.to_excel(writer, sheet_name="Quartal_Destination", index=False)
                airline_quarter.to_excel(writer, sheet_name="Quartal_Airline", index=False)
                history_df.to_excel(writer, sheet_name="Check_Import", index=False)
        except Exception as e:
            QMessageBox.critical(self, "Fehler", str(e))
        finally:
            session.close()

    def edit_wch_mapping(self):
        dialog = WchMappingDialog(self)
        dialog.exec()
        self.refresh_filters()
        self.refresh_stats()

    def edit_destination_mapping(self):
        dialog = DestinationMappingDialog(self)
        dialog.exec()
        self.refresh_filters()
        self.refresh_stats()

    def edit_airline_mapping(self):
        dialog = AirlineMappingDialog(self)
        dialog.exec()
        self.refresh_filters()
        self.refresh_stats()

    def edit_flight_mapping(self):
        dialog = FlightDestinationMappingDialog(self)
        dialog.exec()
        self.refresh_filters()
        self.refresh_stats()

    def delete_selected_import(self):
        if self.tabs.currentWidget() is not self.tab_history:
            QMessageBox.information(self, "Hinweis", "Bitte den Tab 'Import-Historie' auswaehlen.")
            return

        row = self.tab_history.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hinweis", "Bitte einen Import in der Historie auswaehlen.")
            return

        source_file = self.tab_history.item(row, 3)
        source_file = source_file.text() if source_file else None
        if not source_file:
            return

        confirm = QMessageBox.question(
            self,
            "Bestaetigen",
            f"Import loeschen?\n{source_file}",
        )
        if confirm != QMessageBox.Yes:
            return

        session = SessionLocal()
        try:
            imports = session.query(ImportFile).filter(ImportFile.source_file == source_file).all()
            for imp in imports:
                session.query(PrmAnnouncement).filter(PrmAnnouncement.import_id == imp.id).delete()
                session.query(DpaxDailySummary).filter(DpaxDailySummary.import_id == imp.id).delete()
                session.delete(imp)
            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        self.refresh_filters()
        self.refresh_stats()

    def _set_combo_values(self, combo: QComboBox, values: list[str]):
        current = self._current_value(combo)
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Alle", None)
        for value in values:
            combo.addItem(str(value), value)
        if current is not None:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _current_value(self, combo: QComboBox):
        if combo.count() == 0:
            return None
        return combo.currentData()

    def _apply_filter_defaults(self):
        month = FILTER_DEFAULTS.get("month")
        in_out = FILTER_DEFAULTS.get("in_out")
        airline = FILTER_DEFAULTS.get("airline")
        wch_type = FILTER_DEFAULTS.get("wch_type")

        if month is not None:
            self._select_combo_value(self.cmb_month, month)
        if in_out is not None:
            self._select_combo_value(self.cmb_inout, in_out)
        if airline is not None:
            self._select_combo_value(self.cmb_airline, airline)
        if wch_type is not None:
            self._select_combo_value(self.cmb_wch, wch_type)

    def _select_combo_value(self, combo: QComboBox, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def show_df(self, table: QTableWidget, df: pd.DataFrame):
        table.clear()
        table.setRowCount(len(df))
        table.setColumnCount(len(df.columns))
        table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r in range(len(df)):
            for c, col in enumerate(df.columns):
                v = df.iloc[r, c]
                table.setItem(r, c, QTableWidgetItem("" if pd.isna(v) else str(v)))
        table.resizeColumnsToContents()

    def update_mapping_status(self):
        session = SessionLocal()
        try:
            wch_unmapped = 0
            values = session.query(PrmAnnouncement.wch_type).distinct().all()
            for (val,) in values:
                if val and map_wch_category(val, session) is None:
                    wch_unmapped += 1

            dest_unmapped = 0
            values = session.query(PrmAnnouncement.airport).distinct().all()
            for (val,) in values:
                if val and map_destination(val, session) is None:
                    dest_unmapped += 1

            airline_unmapped = 0
            values = session.query(
                PrmAnnouncement.airline_raw, PrmAnnouncement.airline_code
            ).distinct().all()
            for raw_val, code_val in values:
                source = raw_val or code_val
                if source and map_airline(source, session) is None:
                    airline_unmapped += 1

            flight_unmapped = 0
            values = session.query(
                PrmAnnouncement.airline_raw,
                PrmAnnouncement.airline_code,
                PrmAnnouncement.flight_no,
                PrmAnnouncement.airport_code,
            ).filter(PrmAnnouncement.flight_no.isnot(None)).distinct().all()
            for raw_val, code_val, flight_no, airport_code in values:
                if airport_code:
                    continue
                airline_value = raw_val or code_val
                if airline_value and map_flight_destination(airline_value, flight_no, session) is None:
                    flight_unmapped += 1
        finally:
            session.close()

        self._set_status_label(self.lbl_wch_status, "WCH", wch_unmapped)
        self._set_status_label(self.lbl_dest_status, "Dest", dest_unmapped)
        self._set_status_label(self.lbl_airline_status, "Airline", airline_unmapped)
        self._set_status_label(self.lbl_flight_status, "Flight", flight_unmapped)

    def _set_status_label(self, label: QLabel, name: str, count: int):
        if count == 0:
            label.setText(f"{name}: OK")
            label.setStyleSheet("background:#d9ead3; padding:2px 6px; border-radius:4px;")
        else:
            label.setText(f"{name}: {count} offen")
            label.setStyleSheet("background:#f4cccc; padding:2px 6px; border-radius:4px;")

def run_app():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


class WchMappingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("WCH Mapping bearbeiten")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.tbl_mapping = QTableWidget()
        self.tbl_mapping.setColumnCount(4)
        self.tbl_mapping.setHorizontalHeaderLabels(["Raw", "Code", "Kategorie", "Quelle"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mapping.setEditTriggers(QAbstractItemView.AllEditTriggers)
        layout.addWidget(QLabel("Mapping"))
        layout.addWidget(self.tbl_mapping)

        self.tbl_unmapped = QTableWidget()
        self.tbl_unmapped.setColumnCount(4)
        self.tbl_unmapped.setHorizontalHeaderLabels(["Nicht zugeordnet (RAW)", "Code", "Kategorie", "Quelle"])
        self.tbl_unmapped.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_unmapped.setEditTriggers(QAbstractItemView.AllEditTriggers)
        layout.addWidget(QLabel("Nicht zugeordnete Werte"))
        layout.addWidget(self.tbl_unmapped)

        row = QHBoxLayout()
        btn_add = QPushButton("Zeile hinzufuegen")
        btn_add.clicked.connect(self.add_row)
        btn_new = QPushButton("Neue Kategorie")
        btn_new.clicked.connect(self.add_category)
        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self.load_data)
        btn_save_unmapped = QPushButton("Nicht zugeordnete uebernehmen")
        btn_save_unmapped.clicked.connect(self.save_unmapped)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self.save_mapping)
        btn_close = QPushButton("Schliessen")
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_add)
        row.addWidget(btn_new)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(btn_save_unmapped)
        row.addWidget(btn_save)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self.load_data()

    def add_row(self):
        r = self.tbl_mapping.rowCount()
        self.tbl_mapping.insertRow(r)

    def add_category(self):
        dialog = WchCategoryDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        raw, code_norm, name_norm = dialog.values()
        if not raw or not code_norm or not name_norm:
            return
        raw_key = self._normalize_raw(raw)
        if not raw_key:
            QMessageBox.critical(self, "Fehler", "Ungueltiger RAW-Wert.")
            return

        session = SessionLocal()
        try:
            session.merge(
                RefWchType(
                    raw_value=raw_key,
                    category_code=code_norm,
                    category_name=name_norm,
                    mapping_source="manual",
                )
            )
            session.query(PrmAnnouncement).filter(
                PrmAnnouncement.wch_type == raw
            ).update(
                {PrmAnnouncement.wch_category: name_norm},
                synchronize_session=False,
            )
            session.commit()
            self._save_mapping_file(self._current_mapping_rows(session))
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        self.load_data()

    def load_data(self):
        session = SessionLocal()
        try:
            rows = session.query(RefWchType).order_by(RefWchType.raw_value).all()
            self.tbl_mapping.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tbl_mapping.setItem(i, 0, self._editable_item(row.raw_value or ""))
                self.tbl_mapping.setItem(i, 1, self._editable_item(row.category_code or ""))
                self.tbl_mapping.setItem(i, 2, self._editable_item(row.category_name or ""))
                source = row.mapping_source or "auto"
                self.tbl_mapping.setCellWidget(i, 3, self._source_combo(source))

            unmapped = []
            values = session.query(PrmAnnouncement.wch_type).distinct().all()
            for (val,) in values:
                if val and map_wch_category(val, session) is None:
                    unmapped.append(str(val))
            unmapped = sorted(set(unmapped))
            self.tbl_unmapped.setRowCount(len(unmapped))
            for i, val in enumerate(unmapped):
                self.tbl_unmapped.setItem(i, 0, self._editable_item(val))
                self.tbl_unmapped.setItem(i, 1, self._editable_item(""))
                self.tbl_unmapped.setItem(i, 2, self._editable_item(""))
                self.tbl_unmapped.setItem(i, 3, self._readonly_item("manual"))
        finally:
            session.close()

    def _normalize_category(self, code: str | None, name: str | None):
        if code and name:
            return code.strip().upper(), name.strip().upper()
        if name:
            key = name.strip().upper()
            if key == "STRETCHER":
                return "ST", "STRETCHER"
            if key in {"WCHR", "WCHS", "WCHC", "BLIND", "TAUB", "MAAS"}:
                return {
                    "WCHR": "R",
                    "WCHS": "S",
                    "WCHC": "C",
                    "BLIND": "B",
                    "TAUB": "T",
                    "MAAS": "M",
                }[key], key
        if code:
            key = code.strip().upper()
            if key in CATEGORY_MAP:
                return key, CATEGORY_MAP[key]
        return None, None

    def save_mapping(self):
        data = []
        for r in range(self.tbl_mapping.rowCount()):
            raw = self._cell_text(self.tbl_mapping, r, 0)
            code = self._cell_text(self.tbl_mapping, r, 1)
            name = self._cell_text(self.tbl_mapping, r, 2)
            source = self._source_value(self.tbl_mapping, r, 3)
            if not raw:
                continue
            code_norm, name_norm = self._normalize_category(code, name)
            if not code_norm or not name_norm:
                QMessageBox.critical(self, "Fehler", f"Ungueltige Kategorie in Zeile {r+1}.")
                return
            raw_key = self._normalize_raw(raw)
            if not raw_key:
                QMessageBox.critical(self, "Fehler", f"Ungueltiger RAW-Wert in Zeile {r+1}.")
                return
            data.append((raw, raw_key, code_norm, name_norm, source))

        session = SessionLocal()
        try:
            session.query(RefWchType).delete()
            for raw, raw_key, code_norm, name_norm, source in data:
                session.add(
                    RefWchType(
                        raw_value=raw_key,
                        category_code=code_norm,
                        category_name=name_norm,
                        mapping_source=source or "manual",
                    )
                )
            session.commit()
            self._save_mapping_file(self._current_mapping_rows(session))
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Mapping gespeichert.")
        self.load_data()

    def save_unmapped(self):
        data = []
        invalid_rows = []
        for r in range(self.tbl_unmapped.rowCount()):
            raw = self._cell_text(self.tbl_unmapped, r, 0)
            code = self._cell_text(self.tbl_unmapped, r, 1)
            name = self._cell_text(self.tbl_unmapped, r, 2)
            if not raw and not code and not name:
                continue
            if not raw:
                QMessageBox.critical(self, "Fehler", f"Wert fehlt in Zeile {r+1}.")
                return
            code_norm, name_norm = self._normalize_category(code, name)
            if not code_norm or not name_norm:
                invalid_rows.append((r + 1, code or name))
                continue
            raw_key = self._normalize_raw(raw)
            if not raw_key:
                invalid_rows.append((r + 1, raw))
                continue
            data.append((raw, raw_key, code_norm, name_norm))

        if invalid_rows and not data:
            details = ", ".join([f"{row}:{val}" for row, val in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.critical(
                self,
                "Fehler",
                f"Ungueltige Kategorie in Zeilen: {details}{more}.",
            )
            return

        if not data:
            return

        session = SessionLocal()
        try:
            for raw, raw_key, code_norm, name_norm in data:
                session.merge(
                    RefWchType(
                        raw_value=raw_key,
                        category_code=code_norm,
                        category_name=name_norm,
                        mapping_source="manual",
                    )
                )
                session.query(PrmAnnouncement).filter(
                    PrmAnnouncement.wch_type == raw
                ).update(
                    {PrmAnnouncement.wch_category: name_norm},
                    synchronize_session=False,
                )
            session.commit()
            self._save_mapping_file(self._current_mapping_rows(session))
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Nicht zugeordnete Werte gespeichert.")
        self.load_data()
        if invalid_rows:
            details = ", ".join([f"{row}:{val}" for row, val in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.warning(
                self,
                "Hinweis",
                f"Einige Eintraege wurden uebersprungen: {details}{more}.",
            )

    def _save_mapping_file(self, data):
        if not WCH_MAPPING_FILE:
            return
        try:
            df = pd.DataFrame(data, columns=["IATA", "Name", "Kategorie"])
            df = df[["IATA", "Name"]]
            path = str(WCH_MAPPING_FILE)
            if os.path.exists(path):
                with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
                    df.to_excel(writer, sheet_name="WCH Kat", index=False)
            else:
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    df.to_excel(writer, sheet_name="WCH Kat", index=False)
        except Exception:
            pass

    def _normalize_raw(self, raw: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", raw.upper().strip())

    def _current_mapping_rows(self, session):
        rows = session.query(RefWchType).order_by(RefWchType.raw_value).all()
        return [(r.raw_value or "", r.category_code or "", r.category_name or "") for r in rows]

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _editable_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        return item

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _source_combo(self, value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("auto")
        combo.addItem("manual")
        index = combo.findText(value or "auto")
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _source_value(self, table: QTableWidget, row: int, col: int) -> str:
        widget = table.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return self._cell_text(table, row, col)


class WchCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neue WCH Kategorie")
        self.resize(420, 180)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.txt_raw = QLineEdit()
        self.txt_code = QLineEdit()
        self.txt_name = QLineEdit()
        form.addRow("RAW", self.txt_raw)
        form.addRow("Code", self.txt_code)
        form.addRow("Kategorie", self.txt_name)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        raw = self.txt_raw.text().strip()
        code = self.txt_code.text().strip()
        name = self.txt_name.text().strip()
        code_norm, name_norm = WchMappingDialog._normalize_category(self, code, name)
        if not raw or not code_norm or not name_norm:
            QMessageBox.critical(self, "Fehler", "Bitte RAW, Code oder Kategorie korrekt ausfuellen.")
            return None, None, None
        return raw, code_norm, name_norm


class DestinationMappingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Destination Mapping bearbeiten")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        mapped_tab = QWidget()
        mapped_layout = QVBoxLayout(mapped_tab)
        mapped_layout.addWidget(QLabel("Alle Zuordnungen"))
        self.tbl_mapping = QTableWidget()
        self.tbl_mapping.setColumnCount(4)
        self.tbl_mapping.setHorizontalHeaderLabels(["RAW", "IATA3", "Destination", "Quelle"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mapping.setEditTriggers(QAbstractItemView.AllEditTriggers)
        mapped_layout.addWidget(self.tbl_mapping)
        self.tabs.addTab(mapped_tab, "Alle Zuordnungen")

        unmapped_tab = QWidget()
        unmapped_layout = QVBoxLayout(unmapped_tab)
        unmapped_layout.addWidget(QLabel("Nicht zugeordnete Destinationen"))
        self.tbl_unmapped = QTableWidget()
        self.tbl_unmapped.setColumnCount(2)
        self.tbl_unmapped.setHorizontalHeaderLabels(["Nicht zugeordnet (RAW)", "IATA3"])
        self.tbl_unmapped.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_unmapped.setEditTriggers(QAbstractItemView.AllEditTriggers)
        unmapped_layout.addWidget(self.tbl_unmapped)
        self.tabs.addTab(unmapped_tab, "Nicht zugeordnet")

        row = QHBoxLayout()
        btn_add = QPushButton("Zeile hinzufuegen")
        btn_add.clicked.connect(self.add_row)
        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self.load_data)
        btn_save_unmapped = QPushButton("Nicht zugeordnete uebernehmen")
        btn_save_unmapped.clicked.connect(self.save_unmapped)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self.save_mapping)
        btn_close = QPushButton("Schliessen")
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_add)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(btn_save_unmapped)
        row.addWidget(btn_save)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self.load_data()

    def add_row(self):
        r = self.tbl_mapping.rowCount()
        self.tbl_mapping.insertRow(r)
        self.tbl_mapping.setItem(r, 0, self._editable_item(""))
        self.tbl_mapping.setItem(r, 1, self._editable_item(""))
        self.tbl_mapping.setItem(r, 2, self._editable_item(""))

    def load_data(self):
        session = SessionLocal()
        try:
            rows = session.query(RefDestination).order_by(RefDestination.raw_value).all()
            self.tbl_mapping.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tbl_mapping.setItem(i, 0, self._editable_item(row.raw_value or ""))
                self.tbl_mapping.setItem(i, 1, self._editable_item(row.iata3 or ""))
                display_name = row.display_name or row.raw_value
                self.tbl_mapping.setItem(i, 2, self._editable_item(display_name or ""))
                source = row.mapping_source or "auto"
                self.tbl_mapping.setCellWidget(i, 3, self._source_combo(source))

            unmapped = []
            values = session.query(PrmAnnouncement.airport).distinct().all()
            for (val,) in values:
                if val and map_destination(val, session) is None:
                    unmapped.append(str(val))
            unmapped = sorted(set(unmapped))
            self.tbl_unmapped.setRowCount(len(unmapped))
            for i, val in enumerate(unmapped):
                self.tbl_unmapped.setItem(i, 0, self._editable_item(val))
                self.tbl_unmapped.setItem(i, 1, self._editable_item(""))
        finally:
            session.close()

    def save_mapping(self):
        data = []
        for r in range(self.tbl_mapping.rowCount()):
            raw_display = self._cell_text(self.tbl_mapping, r, 0)
            iata = self._cell_text(self.tbl_mapping, r, 1).upper()
            name = self._cell_text(self.tbl_mapping, r, 2)
            source = self._source_value(self.tbl_mapping, r, 3)
            if not raw_display:
                continue
            if not iata or len(iata) != 3:
                QMessageBox.critical(self, "Fehler", f"Ungueltiger IATA3 in Zeile {r+1}.")
                return
            if not name:
                name = raw_display
            raw_key = normalize_destination_key(raw_display)
            if not raw_key:
                continue
            data.append((raw_key, iata, name, source))

        unique_data = {}
        for raw_key, iata, name, source in data:
            unique_data[raw_key] = (iata, name, source)

        session = SessionLocal()
        try:
            airports = session.query(PrmAnnouncement.airport).distinct().all()
            airport_by_key = {}
            for (val,) in airports:
                if not val:
                    continue
                key = normalize_destination_key(str(val))
                if not key:
                    continue
                airport_by_key.setdefault(key, set()).add(str(val))

            session.query(RefDestination).delete()
            for raw_key, (iata, name, source) in unique_data.items():
                session.merge(
                    RefDestination(
                        raw_value=raw_key,
                        iata3=iata,
                        display_name=name,
                        mapping_source=source or "manual",
                    )
                )
                raw_values = set(airport_by_key.get(raw_key, set()))
                if name:
                    raw_values.add(name)
                for raw_value in raw_values:
                    session.query(PrmAnnouncement).filter(
                        PrmAnnouncement.airport == raw_value
                    ).update(
                        {PrmAnnouncement.airport_code: iata}, synchronize_session=False
                    )

            session.commit()
            self._save_mapping_file([(r, i, n) for r, i, n, _ in data])
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Mapping gespeichert.")
        self.load_data()

    def save_unmapped(self):
        data = []
        invalid_rows = []
        for r in range(self.tbl_unmapped.rowCount()):
            raw = self._cell_text(self.tbl_unmapped, r, 0)
            iata = self._cell_text(self.tbl_unmapped, r, 1).upper()
            if not raw and not iata:
                continue
            if not raw and iata:
                QMessageBox.critical(self, "Fehler", f"Wert fehlt in Zeile {r+1}.")
                return
            if not iata:
                # Skip rows without a code; user may fill them later.
                continue
            if len(iata) != 3:
                invalid_rows.append((r + 1, iata))
                continue
            raw_key = normalize_destination_key(raw)
            if not raw_key:
                continue
            data.append((raw_key, iata, raw))

        if invalid_rows and not data:
            details = ", ".join([f"{row}:{code}" for row, code in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.critical(
                self,
                "Fehler",
                f"Ungueltige IATA3 in Zeilen: {details}{more}.",
            )
            return

        if not data:
            return

        session = SessionLocal()
        try:
            airports = session.query(PrmAnnouncement.airport).distinct().all()
            airport_by_key = {}
            for (val,) in airports:
                if not val:
                    continue
                key = normalize_destination_key(str(val))
                if not key:
                    continue
                airport_by_key.setdefault(key, set()).add(str(val))

            for raw_key, iata, display_name in data:
                session.merge(
                    RefDestination(
                        raw_value=raw_key,
                        iata3=iata,
                        display_name=display_name,
                        mapping_source="manual",
                    )
                )
                raw_values = set(airport_by_key.get(raw_key, set()))
                if display_name:
                    raw_values.add(display_name)
                for raw_value in raw_values:
                    session.query(PrmAnnouncement).filter(
                        PrmAnnouncement.airport == raw_value
                    ).update(
                        {PrmAnnouncement.airport_code: iata}, synchronize_session=False
                    )

            session.commit()
            self._save_mapping_file(self._current_mapping_rows(session))
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Nicht zugeordnete Werte gespeichert.")
        self.load_data()
        if invalid_rows:
            details = ", ".join([f"{row}:{code}" for row, code in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.warning(
                self,
                "Hinweis",
                f"Einige Eintraege wurden uebersprungen (IATA3 ungueltig): {details}{more}.",
            )

    def _current_mapping_rows(self, session):
        rows = session.query(RefDestination).order_by(RefDestination.raw_value).all()
        return [
            (r.raw_value or "", r.iata3 or "", r.display_name or r.raw_value or "")
            for r in rows
        ]

    def _save_mapping_file(self, data):
        if not DESTINATION_MAPPING_FILE:
            return
        try:
            df = pd.DataFrame(data, columns=["RawKey", "IATA", "Name"])
            df = df[df["IATA"].astype(str).str.len() == 3]
            df = df[df["Name"].astype(str).str.len() > 0]
            df = df.drop_duplicates(subset=["IATA", "Name"], keep="first")
            df = df[["IATA", "Name"]]
            path = str(DESTINATION_MAPPING_FILE)
            if os.path.exists(path):
                with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
                    df.to_excel(writer, sheet_name="Destinations", index=False)
            else:
                with pd.ExcelWriter(path, engine="openpyxl") as writer:
                    df.to_excel(writer, sheet_name="Destinations", index=False)
        except Exception:
            pass

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _editable_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        return item

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _source_combo(self, value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("auto")
        combo.addItem("manual")
        index = combo.findText(value or "auto")
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _source_value(self, table: QTableWidget, row: int, col: int) -> str:
        widget = table.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return self._cell_text(table, row, col)


class AirlineMappingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Airline Mapping bearbeiten")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        mapped_tab = QWidget()
        mapped_layout = QVBoxLayout(mapped_tab)
        mapped_layout.addWidget(QLabel("Alle Zuordnungen"))
        self.tbl_mapping = QTableWidget()
        self.tbl_mapping.setColumnCount(4)
        self.tbl_mapping.setHorizontalHeaderLabels(["RAW", "IATA2", "Airline", "Quelle"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mapping.setEditTriggers(QAbstractItemView.AllEditTriggers)
        mapped_layout.addWidget(self.tbl_mapping)
        self.tabs.addTab(mapped_tab, "Alle Zuordnungen")

        unmapped_tab = QWidget()
        unmapped_layout = QVBoxLayout(unmapped_tab)
        unmapped_layout.addWidget(QLabel("Nicht zugeordnete Airlines"))
        unmapped_layout.addWidget(
            QLabel(
                "Hinweis: Dispo-Fehleintraege werden hier manuell auf IATA2 gemappt."
            )
        )
        self.tbl_unmapped = QTableWidget()
        self.tbl_unmapped.setColumnCount(2)
        self.tbl_unmapped.setHorizontalHeaderLabels(["Nicht zugeordnet (RAW)", "IATA2"])
        self.tbl_unmapped.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_unmapped.setEditTriggers(QAbstractItemView.AllEditTriggers)
        unmapped_layout.addWidget(self.tbl_unmapped)
        self.tabs.addTab(unmapped_tab, "Nicht zugeordnet")

        row = QHBoxLayout()
        btn_add = QPushButton("Zeile hinzufuegen")
        btn_add.clicked.connect(self.add_row)
        btn_add_fix = QPushButton("Korrektur hinzufuegen")
        btn_add_fix.clicked.connect(self.add_fix_row)
        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self.load_data)
        btn_save_unmapped = QPushButton("Nicht zugeordnete uebernehmen")
        btn_save_unmapped.clicked.connect(self.save_unmapped)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self.save_mapping)
        btn_save_fix = QPushButton("Korrekturen speichern")
        btn_save_fix.clicked.connect(self.save_fixes)
        btn_close = QPushButton("Schliessen")
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_add)
        row.addWidget(btn_add_fix)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(btn_save_unmapped)
        row.addWidget(btn_save)
        row.addWidget(btn_save_fix)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self.load_data()

    def add_row(self):
        r = self.tbl_mapping.rowCount()
        self.tbl_mapping.insertRow(r)
        self.tbl_mapping.setItem(r, 0, self._editable_item(""))
        self.tbl_mapping.setItem(r, 1, self._editable_item(""))
        self.tbl_mapping.setItem(r, 2, self._editable_item(""))

    def add_fix_row(self):
        r = self.tbl_fix.rowCount()
        self.tbl_fix.insertRow(r)
        self.tbl_fix.setItem(r, 0, self._editable_item(""))
        self.tbl_fix.setItem(r, 1, self._editable_item(""))
        self.tbl_fix.setItem(r, 2, self._editable_item(""))
        self.tbl_fix.setItem(r, 3, self._editable_item(""))
        self.tbl_fix.setCellWidget(r, 4, self._source_combo("manual"))

    def load_data(self):
        session = SessionLocal()
        try:
            rows = session.query(RefAirlineMap).order_by(RefAirlineMap.raw_value).all()
            self.tbl_mapping.setRowCount(len(rows))
            for i, row in enumerate(rows):
                display_name = row.display_name or row.raw_value
                self.tbl_mapping.setItem(i, 0, self._editable_item(row.raw_value or ""))
                self.tbl_mapping.setItem(i, 1, self._editable_item(row.iata2 or ""))
                self.tbl_mapping.setItem(i, 2, self._editable_item(display_name or ""))
                source = row.mapping_source or "auto"
                self.tbl_mapping.setCellWidget(i, 3, self._source_combo(source))

            unmapped = []
            values = session.query(PrmAnnouncement.airline_raw, PrmAnnouncement.airline_code).distinct().all()
            for raw_val, code_val in values:
                source = code_val or raw_val
                if not source:
                    continue
                if map_airline(source, session) is None:
                    unmapped.append(str(source))
            unmapped = sorted(set(unmapped))
            self.tbl_unmapped.setRowCount(len(unmapped))
            for i, val in enumerate(unmapped):
                self.tbl_unmapped.setItem(i, 0, self._editable_item(val))
                self.tbl_unmapped.setItem(i, 1, self._editable_item(""))
        finally:
            session.close()

    def save_mapping(self):
        data = []
        for r in range(self.tbl_mapping.rowCount()):
            raw_display = self._cell_text(self.tbl_mapping, r, 0)
            iata = self._cell_text(self.tbl_mapping, r, 1).upper()
            name = self._cell_text(self.tbl_mapping, r, 2)
            source = self._source_value(self.tbl_mapping, r, 3)
            if not raw_display:
                continue
            if not iata or len(iata) != 2:
                QMessageBox.critical(self, "Fehler", f"Ungueltiger IATA2 in Zeile {r+1}.")
                return
            if not name:
                name = raw_display
            raw_key = normalize_airline_key(raw_display)
            if not raw_key:
                continue
            data.append((raw_key, iata, name, source))

        unique_data = {}
        for raw_key, iata, name, source in data:
            unique_data[raw_key] = (iata, name, source)

        session = SessionLocal()
        try:
            values = session.query(PrmAnnouncement.airline_raw, PrmAnnouncement.airline_code).distinct().all()
            airline_by_key = {}
            for raw_val, code_val in values:
                sources = []
                if code_val:
                    sources.append(code_val)
                if raw_val and raw_val != code_val:
                    sources.append(raw_val)
                for source in sources:
                    key = normalize_airline_key(str(source))
                    if not key:
                        continue
                    airline_by_key.setdefault(key, set()).add(str(source))

            session.query(RefAirlineMap).delete()
            for raw_key, (iata, name, source) in unique_data.items():
                session.merge(
                    RefAirlineMap(
                        raw_value=raw_key,
                        iata2=iata,
                        display_name=name,
                        mapping_source=source or "manual",
                    )
                )
                raw_values = set(airline_by_key.get(raw_key, set()))
                if name:
                    raw_values.add(name)
                for raw_value in raw_values:
                    session.query(PrmAnnouncement).filter(
                        (PrmAnnouncement.airline_raw == raw_value)
                        | ((PrmAnnouncement.airline_raw.is_(None)) & (PrmAnnouncement.airline_code == raw_value))
                    ).update(
                        {PrmAnnouncement.airline_code: iata}, synchronize_session=False
                    )

            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Airline Mapping gespeichert.")
        self.load_data()

    def save_unmapped(self):
        data = []
        invalid_rows = []
        for r in range(self.tbl_unmapped.rowCount()):
            raw = self._cell_text(self.tbl_unmapped, r, 0)
            iata = self._cell_text(self.tbl_unmapped, r, 1).upper()
            if not raw and not iata:
                continue
            if not raw and iata:
                QMessageBox.critical(self, "Fehler", f"Wert fehlt in Zeile {r+1}.")
                return
            if not iata:
                continue
            if len(iata) != 2:
                invalid_rows.append((r + 1, iata))
                continue
            raw_key = normalize_airline_key(raw)
            if not raw_key:
                continue
            data.append((raw_key, iata, raw))

        if invalid_rows and not data:
            details = ", ".join([f"{row}:{code}" for row, code in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.critical(
                self,
                "Fehler",
                f"Ungueltige IATA2 in Zeilen: {details}{more}.",
            )
            return

        if not data:
            return

        session = SessionLocal()
        try:
            values = session.query(PrmAnnouncement.airline_raw, PrmAnnouncement.airline_code).distinct().all()
            airline_by_key = {}
            for raw_val, code_val in values:
                source = raw_val or code_val
                if not source:
                    continue
                key = normalize_airline_key(str(source))
                if not key:
                    continue
                airline_by_key.setdefault(key, set()).add(str(source))

            for raw_key, iata, display_name in data:
                session.merge(
                    RefAirlineMap(
                        raw_value=raw_key,
                        iata2=iata,
                        display_name=display_name,
                        mapping_source="manual",
                    )
                )
                raw_values = set(airline_by_key.get(raw_key, set()))
                if display_name:
                    raw_values.add(display_name)
                for raw_value in raw_values:
                    session.query(PrmAnnouncement).filter(
                        (PrmAnnouncement.airline_raw == raw_value)
                        | ((PrmAnnouncement.airline_raw.is_(None)) & (PrmAnnouncement.airline_code == raw_value))
                    ).update(
                        {PrmAnnouncement.airline_code: iata}, synchronize_session=False
                    )

            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Nicht zugeordnete Werte gespeichert.")
        self.load_data()
        if invalid_rows:
            details = ", ".join([f"{row}:{code}" for row, code in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.warning(
                self,
                "Hinweis",
                f"Einige Eintraege wurden uebersprungen (IATA2 ungueltig): {details}{more}.",
            )

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _editable_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        return item

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _source_combo(self, value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("auto")
        combo.addItem("manual")
        index = combo.findText(value or "auto")
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _source_value(self, table: QTableWidget, row: int, col: int) -> str:
        widget = table.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return self._cell_text(table, row, col)


class FlightDestinationMappingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Flugnummer Mapping bearbeiten")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        mapped_tab = QWidget()
        mapped_layout = QVBoxLayout(mapped_tab)
        mapped_layout.addWidget(QLabel("Alle Zuordnungen"))
        self.tbl_mapping = QTableWidget()
        self.tbl_mapping.setColumnCount(4)
        self.tbl_mapping.setHorizontalHeaderLabels(["Airline", "FlightNo", "Destination (IATA3)", "Quelle"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mapping.setEditTriggers(QAbstractItemView.AllEditTriggers)
        mapped_layout.addWidget(self.tbl_mapping)
        self.tabs.addTab(mapped_tab, "Alle Zuordnungen")

        unmapped_tab = QWidget()
        unmapped_layout = QVBoxLayout(unmapped_tab)
        unmapped_layout.addWidget(QLabel("Nicht zugeordnete Flugnummern"))
        unmapped_layout.addWidget(
            QLabel("Hinweis: Nur manuell mappen, wenn keine Zuordnung existiert.")
        )
        self.tbl_unmapped = QTableWidget()
        self.tbl_unmapped.setColumnCount(3)
        self.tbl_unmapped.setHorizontalHeaderLabels(["Airline", "FlightNo", "Destination (IATA3)"])
        self.tbl_unmapped.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_unmapped.setEditTriggers(QAbstractItemView.AllEditTriggers)
        unmapped_layout.addWidget(self.tbl_unmapped)
        self.tabs.addTab(unmapped_tab, "Nicht zugeordnet")

        fix_tab = QWidget()
        fix_layout = QVBoxLayout(fix_tab)
        fix_layout.addWidget(QLabel("Flugnummer-Korrekturen"))
        fix_layout.addWidget(
            QLabel("Hinweis: Korrigiert erkannte Flugnummern, z.B. TK 90 -> VF 90.")
        )
        self.tbl_fix = QTableWidget()
        self.tbl_fix.setColumnCount(5)
        self.tbl_fix.setHorizontalHeaderLabels([
            "Airline",
            "FlightNo",
            "Korr. Airline",
            "Korr. FlightNo",
            "Quelle",
        ])
        self.tbl_fix.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_fix.setEditTriggers(QAbstractItemView.AllEditTriggers)
        fix_layout.addWidget(self.tbl_fix)
        self.tabs.addTab(fix_tab, "Korrekturen")

        row = QHBoxLayout()
        btn_add = QPushButton("Zeile hinzufuegen")
        btn_add.clicked.connect(self.add_row)
        btn_add_fix = QPushButton("Korrektur hinzufuegen")
        btn_add_fix.clicked.connect(self.add_fix_row)
        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self.load_data)
        btn_save_unmapped = QPushButton("Nicht zugeordnete uebernehmen")
        btn_save_unmapped.clicked.connect(self.save_unmapped)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self.save_mapping)
        btn_save_fix = QPushButton("Korrekturen speichern")
        btn_save_fix.clicked.connect(self.save_fixes)
        btn_close = QPushButton("Schliessen")
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_add)
        row.addWidget(btn_add_fix)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(btn_save_unmapped)
        row.addWidget(btn_save)
        row.addWidget(btn_save_fix)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self.load_data()

    def add_row(self):
        r = self.tbl_mapping.rowCount()
        self.tbl_mapping.insertRow(r)
        self.tbl_mapping.setItem(r, 0, self._editable_item(""))
        self.tbl_mapping.setItem(r, 1, self._editable_item(""))
        self.tbl_mapping.setItem(r, 2, self._editable_item(""))

    def add_fix_row(self):
        r = self.tbl_fix.rowCount()
        self.tbl_fix.insertRow(r)
        self.tbl_fix.setItem(r, 0, self._editable_item(""))
        self.tbl_fix.setItem(r, 1, self._editable_item(""))
        self.tbl_fix.setItem(r, 2, self._editable_item(""))
        self.tbl_fix.setItem(r, 3, self._editable_item(""))
        self.tbl_fix.setCellWidget(r, 4, self._source_combo("manual"))

    def load_data(self):
        session = SessionLocal()
        try:
            rows = session.query(RefFlightDestination).order_by(
                RefFlightDestination.airline_key,
                RefFlightDestination.flight_no_key,
            ).all()
            self.tbl_mapping.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tbl_mapping.setItem(i, 0, self._editable_item(row.airline_key or ""))
                self.tbl_mapping.setItem(i, 1, self._editable_item(row.flight_no_key or ""))
                self.tbl_mapping.setItem(i, 2, self._editable_item(row.destination_iata3 or ""))
                source = row.mapping_source or "auto"
                self.tbl_mapping.setCellWidget(i, 3, self._source_combo(source))

            unmapped = []
            values = session.query(
                PrmAnnouncement.airline_raw,
                PrmAnnouncement.airline_code,
                PrmAnnouncement.flight_no,
                PrmAnnouncement.airport_code,
            ).filter(PrmAnnouncement.flight_no.isnot(None)).distinct().all()

            for raw_val, code_val, flight_no, airport_code in values:
                if airport_code:
                    continue
                airline_value = code_val or raw_val
                if not airline_value:
                    continue
                if map_flight_destination(airline_value, flight_no, session) is None:
                    unmapped.append((str(airline_value), str(flight_no)))

            unmapped = sorted(set(unmapped))
            self.tbl_unmapped.setRowCount(len(unmapped))
            for i, (airline_value, flight_no) in enumerate(unmapped):
                self.tbl_unmapped.setItem(i, 0, self._editable_item(airline_value))
                self.tbl_unmapped.setItem(i, 1, self._editable_item(flight_no))
                self.tbl_unmapped.setItem(i, 2, self._editable_item(""))

            rows = session.query(RefFlightNumberFix).order_by(
                RefFlightNumberFix.airline_key,
                RefFlightNumberFix.flight_no_key,
            ).all()
            self.tbl_fix.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tbl_fix.setItem(i, 0, self._editable_item(row.airline_key or ""))
                self.tbl_fix.setItem(i, 1, self._editable_item(row.flight_no_key or ""))
                self.tbl_fix.setItem(i, 2, self._editable_item(row.corrected_airline or ""))
                self.tbl_fix.setItem(i, 3, self._editable_item(row.corrected_flight_no or ""))
                source = row.mapping_source or "auto"
                self.tbl_fix.setCellWidget(i, 4, self._source_combo(source))
        finally:
            session.close()

    def save_mapping(self):
        data = []
        for r in range(self.tbl_mapping.rowCount()):
            airline_val = self._cell_text(self.tbl_mapping, r, 0)
            flight_no = self._cell_text(self.tbl_mapping, r, 1)
            dest = self._cell_text(self.tbl_mapping, r, 2).upper()
            source = self._source_value(self.tbl_mapping, r, 3)
            if not airline_val or not flight_no:
                continue
            if not dest or len(dest) != 3:
                QMessageBox.critical(self, "Fehler", f"Ungueltiger IATA3 in Zeile {r+1}.")
                return
            airline_key = normalize_airline_key(airline_val)
            flight_key = normalize_flight_no(flight_no)
            if not airline_key or not flight_key:
                continue
            data.append((airline_key, flight_key, dest, source))

        unique_data = {}
        for airline_key, flight_key, dest, source in data:
            unique_data[(airline_key, flight_key)] = (dest, source)

        session = SessionLocal()
        try:
            values = session.query(
                PrmAnnouncement.airline_raw,
                PrmAnnouncement.airline_code,
                PrmAnnouncement.flight_no,
            ).filter(PrmAnnouncement.flight_no.isnot(None)).distinct().all()

            raw_pairs_by_key = {}
            for raw_val, code_val, flight_no in values:
                if not flight_no:
                    continue
                sources = []
                if code_val:
                    sources.append(code_val)
                if raw_val and raw_val != code_val:
                    sources.append(raw_val)
                for airline_value in sources:
                    airline_key = normalize_airline_key(str(airline_value))
                    flight_key = normalize_flight_no(str(flight_no))
                    if not airline_key or not flight_key:
                        continue
                    raw_pairs_by_key.setdefault((airline_key, flight_key), set()).add(
                        (str(airline_value), str(flight_no))
                    )

            session.query(RefFlightDestination).delete()
            for (airline_key, flight_key), (dest, source) in unique_data.items():
                session.merge(
                    RefFlightDestination(
                        airline_key=airline_key,
                        flight_no_key=flight_key,
                        destination_iata3=dest,
                        mapping_source=source or "manual",
                    )
                )
                raw_pairs = raw_pairs_by_key.get((airline_key, flight_key), set())
                for raw_airline, raw_flight in raw_pairs:
                    session.query(PrmAnnouncement).filter(
                        ((PrmAnnouncement.airline_raw == raw_airline) | ((PrmAnnouncement.airline_raw.is_(None)) & (PrmAnnouncement.airline_code == raw_airline)))
                        & (PrmAnnouncement.flight_no == raw_flight)
                    ).update(
                        {PrmAnnouncement.airport_code: dest}, synchronize_session=False
                    )

            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Flugnummer Mapping gespeichert.")
        self.load_data()

    def save_unmapped(self):
        data = []
        invalid_rows = []
        for r in range(self.tbl_unmapped.rowCount()):
            airline_val = self._cell_text(self.tbl_unmapped, r, 0)
            flight_no = self._cell_text(self.tbl_unmapped, r, 1)
            dest = self._cell_text(self.tbl_unmapped, r, 2).upper()
            if not airline_val and not flight_no and not dest:
                continue
            if not airline_val or not flight_no:
                QMessageBox.critical(self, "Fehler", f"Wert fehlt in Zeile {r+1}.")
                return
            if not dest:
                continue
            if len(dest) != 3:
                invalid_rows.append((r + 1, dest))
                continue
            airline_key = normalize_airline_key(airline_val)
            flight_key = normalize_flight_no(flight_no)
            if not airline_key or not flight_key:
                continue
            data.append((airline_key, flight_key, dest, airline_val, flight_no))

        if invalid_rows and not data:
            details = ", ".join([f"{row}:{code}" for row, code in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.critical(
                self,
                "Fehler",
                f"Ungueltige IATA3 in Zeilen: {details}{more}.",
            )
            return

        if not data:
            return

        session = SessionLocal()
        try:
            for airline_key, flight_key, dest, raw_airline, raw_flight in data:
                session.merge(
                    RefFlightDestination(
                        airline_key=airline_key,
                        flight_no_key=flight_key,
                        destination_iata3=dest,
                        mapping_source="manual",
                    )
                )
                session.query(PrmAnnouncement).filter(
                    ((PrmAnnouncement.airline_raw == raw_airline) | ((PrmAnnouncement.airline_raw.is_(None)) & (PrmAnnouncement.airline_code == raw_airline)))
                    & (PrmAnnouncement.flight_no == raw_flight)
                ).update(
                    {PrmAnnouncement.airport_code: dest}, synchronize_session=False
                )

            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Nicht zugeordnete Werte gespeichert.")
        self.load_data()
        if invalid_rows:
            details = ", ".join([f"{row}:{code}" for row, code in invalid_rows[:5]])
            more = "" if len(invalid_rows) <= 5 else f" (+{len(invalid_rows) - 5} weitere)"
            QMessageBox.warning(
                self,
                "Hinweis",
                f"Einige Eintraege wurden uebersprungen (IATA3 ungueltig): {details}{more}.",
            )

    def save_fixes(self):
        data = []
        for r in range(self.tbl_fix.rowCount()):
            airline_val = self._cell_text(self.tbl_fix, r, 0)
            flight_no = self._cell_text(self.tbl_fix, r, 1)
            corr_airline = self._cell_text(self.tbl_fix, r, 2)
            corr_flight = self._cell_text(self.tbl_fix, r, 3)
            source = self._source_value(self.tbl_fix, r, 4)
            if not airline_val and not flight_no and not corr_airline and not corr_flight:
                continue
            if not airline_val or not flight_no:
                QMessageBox.critical(self, "Fehler", f"Wert fehlt in Zeile {r+1}.")
                return
            if not corr_airline and not corr_flight:
                QMessageBox.critical(
                    self,
                    "Fehler",
                    f"Keine Korrektur in Zeile {r+1} angegeben.",
                )
                return
            airline_key = normalize_airline_key(airline_val)
            flight_key = normalize_flight_no(flight_no)
            if not airline_key or not flight_key:
                QMessageBox.critical(self, "Fehler", f"Ungueltige Werte in Zeile {r+1}.")
                return
            data.append((airline_key, flight_key, corr_airline, corr_flight, source))

        unique_data = {}
        for airline_key, flight_key, corr_airline, corr_flight, source in data:
            unique_data[(airline_key, flight_key)] = (corr_airline, corr_flight, source)

        session = SessionLocal()
        try:
            values = session.query(
                PrmAnnouncement.airline_raw,
                PrmAnnouncement.airline_code,
                PrmAnnouncement.flight_no,
            ).filter(PrmAnnouncement.flight_no.isnot(None)).distinct().all()

            raw_pairs_by_key = {}
            for raw_val, code_val, flight_no in values:
                if not flight_no:
                    continue
                sources = []
                if code_val:
                    sources.append(code_val)
                if raw_val and raw_val != code_val:
                    sources.append(raw_val)
                for airline_value in sources:
                    airline_key = normalize_airline_key(str(airline_value))
                    flight_key = normalize_flight_no(str(flight_no))
                    if not airline_key or not flight_key:
                        continue
                    raw_pairs_by_key.setdefault((airline_key, flight_key), set()).add(
                        (raw_val, code_val, flight_no)
                    )

            session.query(RefFlightNumberFix).delete()
            for (airline_key, flight_key), (corr_airline, corr_flight, source) in unique_data.items():
                session.merge(
                    RefFlightNumberFix(
                        airline_key=airline_key,
                        flight_no_key=flight_key,
                        corrected_airline=(corr_airline or None),
                        corrected_flight_no=(corr_flight or None),
                        mapping_source=source or "manual",
                    )
                )

                pairs = raw_pairs_by_key.get((airline_key, flight_key), set())
                for raw_val, code_val, raw_flight in pairs:
                    filters = []
                    if raw_val:
                        filters.append(PrmAnnouncement.airline_raw == raw_val)
                    if code_val:
                        filters.append(PrmAnnouncement.airline_code == code_val)
                    if not filters:
                        continue
                    updates = {}
                    if corr_airline:
                        updates[PrmAnnouncement.airline_code] = corr_airline
                    if corr_flight:
                        updates[PrmAnnouncement.flight_no] = corr_flight
                    if not updates:
                        continue
                    session.query(PrmAnnouncement).filter(
                        PrmAnnouncement.flight_no == raw_flight,
                        or_(*filters),
                    ).update(updates, synchronize_session=False)

            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Korrekturen gespeichert.")
        self.load_data()

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _editable_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        return item

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _source_combo(self, value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("auto")
        combo.addItem("manual")
        index = combo.findText(value or "auto")
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _source_value(self, table: QTableWidget, row: int, col: int) -> str:
        widget = table.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return self._cell_text(table, row, col)
