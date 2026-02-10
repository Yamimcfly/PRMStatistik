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

## Datenbank-Konfiguration

### Standard: SQLite (lokal)
Die Anwendung verwendet standardmäßig SQLite für lokale Entwicklung:
```
DATABASE_URL=sqlite:///data/prm_stats.sqlite
```

### Neon PostgreSQL (empfohlen für Produktiv-Umgebung)

[Neon](https://neon.tech) ist eine serverlose PostgreSQL-Plattform, die sich ideal für Cloud-Deployments eignet.

#### 1. Neon-Projekt erstellen
1. Gehen Sie zu [https://neon.tech](https://neon.tech) und erstellen Sie ein kostenloses Konto
2. Erstellen Sie ein neues Projekt
3. Wählen Sie eine Region (z.B. EU Central für DSGVO-Konformität)
4. Notieren Sie sich den Namen Ihrer Datenbank

#### 2. Connection String kopieren
1. Im Neon-Dashboard finden Sie unter "Connection Details" Ihren Connection String
2. Der Connection String hat folgendes Format:
   ```
   postgresql://username:password@endpoint.neon.tech/dbname
   ```
3. **Wichtig**: Fügen Sie `?sslmode=require` am Ende hinzu, da Neon SSL-Verbindungen erfordert

#### 3. Connection String konfigurieren

**Option A: Über .env-Datei (empfohlen)**
1. Kopieren Sie `.env.example` nach `.env`
2. Setzen Sie die `DATABASE_URL`:
   ```bash
   DATABASE_URL=postgresql://username:password@ep-cool-sound-123456.eu-central-1.aws.neon.tech/prmstatistik?sslmode=require
   ```

**Option B: Über config.json**
```json
{
  "database": {
    "url": "postgresql://username:password@endpoint.neon.tech/dbname?sslmode=require"
  }
}
```

#### 4. Anwendung starten
Die Anwendung erstellt automatisch alle benötigten Tabellen beim ersten Start:
```bash
python -m app
```

#### Fehlerbehebung

**Verbindungsfehler:**
- Überprüfen Sie, dass `?sslmode=require` am Ende der DATABASE_URL steht
- Stellen Sie sicher, dass Benutzername und Passwort korrekt sind
- Prüfen Sie, ob die Netzwerkverbindung funktioniert

**Authentifizierungsfehler:**
- Überprüfen Sie Ihre Neon-Zugangsdaten im Dashboard
- Stellen Sie sicher, dass das Passwort keine Sonderzeichen enthält, die URL-kodiert werden müssen

**SSL/TLS-Fehler:**
- Die DATABASE_URL muss mit `?sslmode=require` enden
- Beispiel: `postgresql://user:pass@endpoint.neon.tech/db?sslmode=require`

### Weitere PostgreSQL-Optionen

Die Anwendung unterstützt auch andere PostgreSQL-Anbieter:
- **Lokales PostgreSQL**: `postgresql://user:pass@localhost:5432/dbname`
- **SQL Server**: `mssql+pyodbc://...` (via ODBC Driver 18)
- **Andere Cloud-Anbieter**: Jeder PostgreSQL-kompatible Dienst

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
