from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QLabel, QHBoxLayout, QTableWidget, QTableWidgetItem, QTabWidget, QMessageBox,
    QComboBox, QDialog, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt
import os
import sys
import pandas as pd

from app.config import (
    IMPORT_DIR,
    EXPORT_DIR,
    GUI_SETTINGS,
    FILTER_DEFAULTS,
    WCH_MAPPING_FILE,
    DESTINATION_MAPPING_FILE,
)
from app.db.session import init_db, SessionLocal
from app.importers.voranmeldungen_excel import can_handle as can_handle_voranmeldungen
from app.importers.voranmeldungen_excel import import_voranmeldungen
from app.importers.dpax_summary_excel import can_handle as can_handle_dpax
from app.importers.dpax_summary_excel import import_dpax_summary
from app.services.statistics import (
    compute_destination_stats,
    compute_airline_stats,
    get_filter_options,
    fetch_import_history,
)
from app.importers.wch_mapping import load_wch_mapping, map_wch_category, CATEGORY_MAP
from app.importers.destination_mapping import (
    load_destination_mapping,
    map_destination,
    normalize_destination_key,
)
from app.db.models import RefWchType, PrmAnnouncement, ImportFile, DpaxDailySummary, RefDestination

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
        row.addWidget(self.lbl)
        row.addStretch(1)
        row.addWidget(btn_pick)
        row.addWidget(btn_refresh)
        row.addWidget(btn_export)
        layout.addLayout(row)

        row_actions = QHBoxLayout()
        btn_wch = QPushButton("WCH Mapping bearbeiten…")
        btn_wch.clicked.connect(self.edit_wch_mapping)
        btn_dest = QPushButton("Destination Mapping bearbeiten…")
        btn_dest.clicked.connect(self.edit_destination_mapping)
        btn_delete_import = QPushButton("Import loeschen")
        btn_delete_import.clicked.connect(self.delete_selected_import)
        row_actions.addWidget(btn_wch)
        row_actions.addWidget(btn_dest)
        row_actions.addWidget(btn_delete_import)
        row_actions.addStretch(1)
        layout.addLayout(row_actions)

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
            for path in paths:
                if can_handle_voranmeldungen(path):
                    imported += import_voranmeldungen(path, session)
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
        self.tbl_mapping.setColumnCount(3)
        self.tbl_mapping.setHorizontalHeaderLabels(["Raw", "Code", "Kategorie"])
        self.tbl_mapping.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(QLabel("Mapping"))
        layout.addWidget(self.tbl_mapping)

        self.tbl_unmapped = QTableWidget()
        self.tbl_unmapped.setColumnCount(1)
        self.tbl_unmapped.setHorizontalHeaderLabels(["Nicht zugeordnet"])
        self.tbl_unmapped.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(QLabel("Nicht zugeordnete Werte"))
        layout.addWidget(self.tbl_unmapped)

        row = QHBoxLayout()
        btn_add = QPushButton("Zeile hinzufuegen")
        btn_add.clicked.connect(self.add_row)
        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self.load_data)
        btn_save = QPushButton("Speichern")
        btn_save.clicked.connect(self.save_mapping)
        btn_close = QPushButton("Schliessen")
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_add)
        row.addWidget(btn_refresh)
        row.addStretch(1)
        row.addWidget(btn_save)
        row.addWidget(btn_close)
        layout.addLayout(row)

        self.load_data()

    def add_row(self):
        r = self.tbl_mapping.rowCount()
        self.tbl_mapping.insertRow(r)

    def load_data(self):
        session = SessionLocal()
        try:
            rows = session.query(RefWchType).order_by(RefWchType.raw_value).all()
            self.tbl_mapping.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.tbl_mapping.setItem(i, 0, QTableWidgetItem(row.raw_value or ""))
                self.tbl_mapping.setItem(i, 1, QTableWidgetItem(row.category_code or ""))
                self.tbl_mapping.setItem(i, 2, QTableWidgetItem(row.category_name or ""))

            unmapped = []
            values = session.query(PrmAnnouncement.wch_type).distinct().all()
            for (val,) in values:
                if val and map_wch_category(val, session) is None:
                    unmapped.append(str(val))
            unmapped = sorted(set(unmapped))
            self.tbl_unmapped.setRowCount(len(unmapped))
            for i, val in enumerate(unmapped):
                self.tbl_unmapped.setItem(i, 0, QTableWidgetItem(val))
        finally:
            session.close()

    def _normalize_category(self, code: str | None, name: str | None):
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
            if not raw:
                continue
            code_norm, name_norm = self._normalize_category(code, name)
            if not code_norm or not name_norm:
                QMessageBox.critical(self, "Fehler", f"Ungueltige Kategorie in Zeile {r+1}.")
                return
            data.append((raw, code_norm, name_norm))

        session = SessionLocal()
        try:
            session.query(RefWchType).delete()
            for raw, code_norm, name_norm in data:
                session.add(RefWchType(raw_value=raw, category_code=code_norm, category_name=name_norm))
            session.commit()
            self._save_mapping_file(data)
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Fehler", str(e))
            return
        finally:
            session.close()

        QMessageBox.information(self, "OK", "Mapping gespeichert.")
        self.load_data()

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

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""


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
        self.tbl_mapping.setColumnCount(3)
        self.tbl_mapping.setHorizontalHeaderLabels(["RAW", "IATA3", "Destination"])
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
            data.append((raw_key, iata, name))

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
            for raw_key, iata, name in data:
                session.add(RefDestination(raw_value=raw_key, iata3=iata, display_name=name))
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
            self._save_mapping_file(data)
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
                    RefDestination(raw_value=raw_key, iata3=iata, display_name=display_name)
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
