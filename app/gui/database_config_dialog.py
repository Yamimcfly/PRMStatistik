"""
Dialog zur visuellen Konfiguration der Datenbank-URL.
Wird angezeigt, wenn keine Datenbankverbindung hergestellt werden kann.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTextEdit, QGroupBox, QFormLayout,
    QMessageBox
)
from PySide6.QtCore import Qt
import os
from pathlib import Path


class DatabaseConfigDialog(QDialog):
    """Dialog zur Konfiguration der Datenbank-Verbindung"""
    
    def __init__(self, parent=None, error_message=None):
        super().__init__(parent)
        self.setWindowTitle("Datenbank-Konfiguration")
        self.setModal(True)
        self.resize(700, 500)
        
        self.database_url = None
        self.error_message = error_message
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Fehlermeldung anzeigen, falls vorhanden
        if self.error_message:
            error_group = QGroupBox("Verbindungsfehler")
            error_layout = QVBoxLayout()
            error_label = QLabel(self.error_message)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #D32F2F; padding: 10px;")
            error_layout.addWidget(error_label)
            error_group.setLayout(error_layout)
            layout.addWidget(error_group)
        
        # Einleitung
        intro_label = QLabel(
            "Bitte konfigurieren Sie die Datenbankverbindung. "
            "Sie können eine lokale SQLite-Datenbank oder eine PostgreSQL-Datenbank (z.B. Neon) verwenden."
        )
        intro_label.setWordWrap(True)
        intro_label.setStyleSheet("padding: 10px;")
        layout.addWidget(intro_label)
        
        # Datenbank-Typ Auswahl
        type_group = QGroupBox("Datenbank-Typ")
        type_layout = QFormLayout()
        
        self.db_type_combo = QComboBox()
        self.db_type_combo.addItems([
            "SQLite (lokal, empfohlen für Entwicklung)",
            "Neon PostgreSQL (empfohlen für Produktion)",
            "Andere PostgreSQL-Datenbank",
            "Benutzerdefinierte URL"
        ])
        self.db_type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addRow("Typ:", self.db_type_combo)
        
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Konfigurationsbereich
        self.config_group = QGroupBox("Verbindungsdetails")
        self.config_layout = QFormLayout()
        
        # SQLite-Felder
        self.sqlite_path = QLineEdit("data/prm_stats.sqlite")
        self.sqlite_path.setPlaceholderText("data/prm_stats.sqlite")
        
        # PostgreSQL-Felder
        self.pg_host = QLineEdit()
        self.pg_host.setPlaceholderText("ep-cool-sound-123.eu-central-1.aws.neon.tech")
        
        self.pg_user = QLineEdit()
        self.pg_user.setPlaceholderText("username")
        
        self.pg_password = QLineEdit()
        self.pg_password.setEchoMode(QLineEdit.Password)
        self.pg_password.setPlaceholderText("password")
        
        self.pg_database = QLineEdit("prmstatistik")
        self.pg_database.setPlaceholderText("prmstatistik")
        
        self.pg_port = QLineEdit("5432")
        self.pg_port.setPlaceholderText("5432")
        
        self.pg_ssl = QComboBox()
        self.pg_ssl.addItems(["require", "prefer", "allow", "disable"])
        
        # Benutzerdefinierte URL
        self.custom_url = QLineEdit()
        self.custom_url.setPlaceholderText(
            "sqlite:///data/prm_stats.sqlite oder postgresql://user:pass@host:5432/db?sslmode=require"
        )
        
        self.config_group.setLayout(self.config_layout)
        layout.addWidget(self.config_group)
        
        # Vorschau der URL
        preview_group = QGroupBox("Verbindungs-URL (Vorschau)")
        preview_layout = QVBoxLayout()
        self.url_preview = QTextEdit()
        self.url_preview.setReadOnly(True)
        self.url_preview.setMaximumHeight(60)
        self.url_preview.setStyleSheet("background-color: #F5F5F5; font-family: monospace;")
        preview_layout.addWidget(self.url_preview)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # Hilfetext
        help_label = QLabel(
            "<b>Hinweis für Neon:</b> Erstellen Sie ein kostenloses Konto unter "
            "<a href='https://neon.tech'>neon.tech</a> und kopieren Sie den Connection String "
            "aus dem Dashboard."
        )
        help_label.setOpenExternalLinks(True)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("padding: 10px; background-color: #E3F2FD;")
        layout.addWidget(help_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.test_button = QPushButton("Verbindung testen")
        self.test_button.clicked.connect(self._test_connection)
        button_layout.addWidget(self.test_button)
        
        self.save_button = QPushButton("Speichern && Verbinden")
        self.save_button.clicked.connect(self._save_and_connect)
        self.save_button.setDefault(True)
        button_layout.addWidget(self.save_button)
        
        cancel_button = QPushButton("Abbrechen")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        # Initial: SQLite anzeigen
        self._on_type_changed(0)
        
        # Verbinde Signale für Live-Vorschau
        self._connect_preview_signals()
    
    def _connect_preview_signals(self):
        """Verbindet alle Eingabefelder mit der URL-Vorschau"""
        self.sqlite_path.textChanged.connect(self._update_preview)
        self.pg_host.textChanged.connect(self._update_preview)
        self.pg_user.textChanged.connect(self._update_preview)
        self.pg_password.textChanged.connect(self._update_preview)
        self.pg_database.textChanged.connect(self._update_preview)
        self.pg_port.textChanged.connect(self._update_preview)
        self.pg_ssl.currentTextChanged.connect(self._update_preview)
        self.custom_url.textChanged.connect(self._update_preview)
    
    def _on_type_changed(self, index):
        """Aktualisiert die Formularfelder basierend auf dem gewählten Typ"""
        # Alle Felder entfernen
        while self.config_layout.count():
            child = self.config_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
        
        if index == 0:  # SQLite
            self.config_layout.addRow("Datei-Pfad:", self.sqlite_path)
            self.sqlite_path.show()
        elif index in [1, 2]:  # PostgreSQL (Neon oder andere)
            self.config_layout.addRow("Host/Endpoint:", self.pg_host)
            self.config_layout.addRow("Benutzername:", self.pg_user)
            self.config_layout.addRow("Passwort:", self.pg_password)
            self.config_layout.addRow("Datenbank:", self.pg_database)
            self.config_layout.addRow("Port:", self.pg_port)
            self.config_layout.addRow("SSL-Modus:", self.pg_ssl)
            self.pg_host.show()
            self.pg_user.show()
            self.pg_password.show()
            self.pg_database.show()
            self.pg_port.show()
            self.pg_ssl.show()
            
            # Für Neon standardmäßig SSL auf "require" setzen
            if index == 1:
                self.pg_ssl.setCurrentText("require")
        else:  # Benutzerdefiniert
            self.config_layout.addRow("Verbindungs-URL:", self.custom_url)
            self.custom_url.show()
        
        self._update_preview()
    
    def _update_preview(self):
        """Aktualisiert die URL-Vorschau"""
        url = self._build_database_url()
        self.url_preview.setPlainText(url)
    
    def _build_database_url(self):
        """Erstellt die Datenbank-URL basierend auf den Eingaben"""
        index = self.db_type_combo.currentIndex()
        
        if index == 0:  # SQLite
            path = self.sqlite_path.text().strip() or "data/prm_stats.sqlite"
            return f"sqlite:///{path}"
        
        elif index in [1, 2]:  # PostgreSQL
            host = self.pg_host.text().strip()
            user = self.pg_user.text().strip()
            password = self.pg_password.text().strip()
            database = self.pg_database.text().strip() or "prmstatistik"
            port = self.pg_port.text().strip() or "5432"
            ssl_mode = self.pg_ssl.currentText()
            
            if not host or not user or not password:
                return "postgresql://[Bitte alle Felder ausfüllen]"
            
            # URL zusammenbauen
            url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
            if ssl_mode != "disable":
                url += f"?sslmode={ssl_mode}"
            return url
        
        else:  # Benutzerdefiniert
            return self.custom_url.text().strip() or "[Bitte URL eingeben]"
    
    def _test_connection(self):
        """Testet die Datenbankverbindung"""
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import OperationalError, DatabaseError
        
        url = self._build_database_url()
        
        if "[" in url or not url:
            QMessageBox.warning(
                self,
                "Ungültige Konfiguration",
                "Bitte füllen Sie alle erforderlichen Felder aus."
            )
            return
        
        try:
            # Verbindung testen
            engine = create_engine(url, future=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            QMessageBox.information(
                self,
                "Verbindung erfolgreich",
                f"Die Verbindung zur Datenbank wurde erfolgreich hergestellt!\n\n"
                f"Datenbank-Typ: {engine.dialect.name}"
            )
        
        except OperationalError as e:
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            QMessageBox.critical(
                self,
                "Verbindungsfehler",
                f"Die Verbindung zur Datenbank ist fehlgeschlagen:\n\n{error_msg}\n\n"
                f"Bitte überprüfen Sie Ihre Eingaben."
            )
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "Fehler",
                f"Ein unerwarteter Fehler ist aufgetreten:\n\n{str(e)}"
            )
    
    def _save_and_connect(self):
        """Speichert die Konfiguration und schließt den Dialog"""
        url = self._build_database_url()
        
        if "[" in url or not url:
            QMessageBox.warning(
                self,
                "Ungültige Konfiguration",
                "Bitte füllen Sie alle erforderlichen Felder aus."
            )
            return
        
        # URL speichern
        self.database_url = url
        
        # In .env-Datei speichern
        try:
            self._save_to_env_file(url)
            QMessageBox.information(
                self,
                "Gespeichert",
                "Die Datenbankverbindung wurde in der .env-Datei gespeichert.\n\n"
                "Die Anwendung wird jetzt mit der neuen Verbindung gestartet."
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(
                self,
                "Warnung",
                f"Die Konfiguration konnte nicht gespeichert werden: {e}\n\n"
                f"Die Verbindung wird trotzdem verwendet."
            )
            self.accept()
    
    def _save_to_env_file(self, url):
        """Speichert die DATABASE_URL in die .env-Datei"""
        # Finde das Projekt-Root-Verzeichnis
        base_dir = Path(__file__).resolve().parents[2]
        env_file = base_dir / ".env"
        
        # Lese existierende .env oder verwende .env.example als Template
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
        else:
            env_example = base_dir / ".env.example"
            if env_example.exists():
                content = env_example.read_text(encoding="utf-8")
            else:
                content = ""
        
        # Ersetze oder füge DATABASE_URL hinzu
        lines = content.split("\n")
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("DATABASE_URL="):
                lines[i] = f"DATABASE_URL={url}"
                updated = True
                break
        
        if not updated:
            # Füge DATABASE_URL hinzu
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"DATABASE_URL={url}")
        
        # Schreibe zurück
        env_file.write_text("\n".join(lines), encoding="utf-8")
    
    def get_database_url(self):
        """Gibt die konfigurierte DATABASE_URL zurück"""
        return self.database_url
