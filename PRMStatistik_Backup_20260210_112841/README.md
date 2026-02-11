# FKB PRM Statistik App (Scaffold)

Python GUI + Datenbank (SQLite lokal, später SQL Server/PostgreSQL möglich) für PRM-Statistiken (Kap1–Kap3).

## Tech-Stack (empfohlen)
- **Python 3.11+**
- **PySide6 (Qt GUI)**
- **SQLAlchemy 2.x** (DB-Abstraktion)
- **pandas + openpyxl** (Excel Import)
- **Alembic** (DB-Migrationen)

## Quickstart
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
python -m app
```

## Konfiguration (config.json)
Kopiere `config.example.json` nach `config.json` und passe die Werte an.
Alle Pfade und Einstellungen liegen in der Datei `config.json` im Projekt-Root.
Wichtig sind insbesondere:
- `database.url` (PostgreSQL DSN, z.B. `postgresql+psycopg://user:pass@host:5432/db`)
- `database.sqlite_source_url` (Quelle fuer Migration)
- `paths.import_dir` / `paths.export_dir`
- `gui.width` / `gui.height`
- `filters.default` (Startfilter)

## Migration SQLite -> PostgreSQL
1) `config.json` auf PostgreSQL-Datenbank anpassen.
2) Ziel-Datenbank muss existieren.
3) Migration starten:
```bash
python -m app.migrate
```
Wenn die Ziel-DB bereits Daten hat, setze `database.migration.overwrite_target` auf `true`.

## Projektstruktur
- `app/gui/` Qt GUI
- `app/importers/` Excel Importer (neu/alt)
- `app/db/` Datenbankmodelle + Session
- `app/services/` Statistik-Berechnung (Kap1–Kap3)
- `data/` Beispiel-/Testdateien (nicht versionieren in echt)

## DB
Standard: `sqlite:///data/prm_stats.sqlite`
Später SQL Server:
- Connection String z.B. `mssql+pyodbc://...` (via ODBC Driver 18)
