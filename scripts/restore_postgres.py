from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _find_psql() -> str | None:
    psql = shutil.which("psql")
    if psql:
        return psql
    for version in ["18", "17", "16", "15", "14", "13"]:
        candidate = Path(f"C:/Program Files/PostgreSQL/{version}/bin/psql.exe")
        if candidate.exists():
            return str(candidate)
    return None


def _pg_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg"):
        return db_url.replace("postgresql+psycopg", "postgresql", 1)
    if db_url.startswith("postgresql+psycopg2"):
        return db_url.replace("postgresql+psycopg2", "postgresql", 1)
    return db_url


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    backup_dir = base_dir / "data" / "backups"

    if not backup_dir.exists():
        raise FileNotFoundError("Backup folder not found: data/backups")

    backups = sorted(
        [p for p in backup_dir.iterdir() if p.is_dir() and p.name.startswith("config_")]
    )
    if not backups:
        raise FileNotFoundError("No backups found.")

    latest = backups[-1]
    dump = latest / "postgres_backup.sql"
    if not dump.exists():
        raise FileNotFoundError("postgres_backup.sql not found in latest backup.")

    config_path = base_dir / "config.json"
    if not config_path.exists():
        raise FileNotFoundError("config.json not found.")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_url = config.get("database", {}).get("url", "")
    if not db_url.startswith("postgresql"):
        raise ValueError("Database URL is not PostgreSQL.")

    psql = _find_psql()
    if not psql:
        raise FileNotFoundError("psql not found. Install PostgreSQL client tools.")

    pg_url = _pg_url(db_url)
    drop_result = subprocess.run(
        [psql, pg_url, "-v", "ON_ERROR_STOP=1", "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"],
        text=True,
    )
    if drop_result.returncode != 0:
        raise RuntimeError("Failed to reset schema before restore.")

    result = subprocess.run(
        [psql, pg_url, "-v", "ON_ERROR_STOP=1", "-f", str(dump)],
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("psql restore failed.")

    print(f"Restored PostgreSQL from: {dump}")


if __name__ == "__main__":
    main()
