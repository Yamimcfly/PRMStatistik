from __future__ import annotations

import json
import shutil
import subprocess
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    backup_dir = base_dir / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = backup_dir / f"config_{stamp}"
    target_dir.mkdir(parents=True, exist_ok=True)

    config_path = base_dir / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))

    paths = config.get("paths", {})
    db_url = config.get("database", {}).get("url", "")
    pg_url = db_url
    if db_url.startswith("postgresql+psycopg"):
        pg_url = db_url.replace("postgresql+psycopg", "postgresql", 1)
    elif db_url.startswith("postgresql+psycopg2"):
        pg_url = db_url.replace("postgresql+psycopg2", "postgresql", 1)

    files = [
        config_path,
        base_dir / ".env",
    ]

    mapping_paths = [
        paths.get("wch_mapping_file", ""),
        paths.get("destination_mapping_file", ""),
        paths.get("airline_mapping_file", ""),
    ]

    copied = []
    for path in files:
        if path.exists():
            shutil.copy2(path, target_dir / path.name)
            copied.append(path.name)

    for path_str in mapping_paths:
        if not path_str:
            continue
        path = Path(path_str)
        if path.exists():
            shutil.copy2(path, target_dir / path.name)
            copied.append(path.name)

    db_copied = False
    if db_url.startswith("sqlite:"):
        parsed = urlparse(db_url)
        db_path = parsed.path.lstrip("/")
        if db_path:
            src = (base_dir / db_path).resolve()
            if src.exists():
                shutil.copy2(src, target_dir / src.name)
                copied.append(src.name)
                db_copied = True
    elif db_url.startswith("postgresql"):
        dump_path = target_dir / "postgres_backup.sql"
        pg_dump = shutil.which("pg_dump")
        if not pg_dump:
            for version in ["18", "17", "16", "15", "14", "13"]:
                candidate = Path(f"C:/Program Files/PostgreSQL/{version}/bin/pg_dump.exe")
                if candidate.exists():
                    pg_dump = str(candidate)
                    break
        if pg_dump:
            result = subprocess.run(
                [pg_dump, pg_url, "-f", str(dump_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                copied.append(dump_path.name)
                db_copied = True
            else:
                print("Warning: pg_dump failed:")
                print(result.stderr.strip())
        else:
            print("Warning: pg_dump not found; PostgreSQL backup skipped.")

    if not copied:
        raise FileNotFoundError("No files found to back up.")

    print(f"Backup written to: {target_dir}")
    print("Files:", ", ".join(copied))
    if db_url.startswith("postgresql") and not db_copied:
        print("Note: PostgreSQL database was not backed up.")


if __name__ == "__main__":
    main()
