from __future__ import annotations

import json
import shutil
from urllib.parse import urlparse
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    backup_dir = base_dir / "data" / "backups"

    if not backup_dir.exists():
        raise FileNotFoundError("Backup folder not found: data/backups")

    backups = sorted(
        [p for p in backup_dir.iterdir() if p.is_dir() and p.name.startswith("config_")]
    )
    if not backups:
        raise FileNotFoundError("No config backups found.")

    latest = backups[-1]

    restored = []
    for name in ["config.json", ".env"]:
        src = latest / name
        if src.exists():
            shutil.copy2(src, base_dir / name)
            restored.append(name)

    config_path = base_dir / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    paths = config.get("paths", {})
    db_url = config.get("database", {}).get("url", "")

    mapping_paths = [
        paths.get("wch_mapping_file", ""),
        paths.get("destination_mapping_file", ""),
        paths.get("airline_mapping_file", ""),
    ]
    for path_str in mapping_paths:
        if not path_str:
            continue
        src = latest / Path(path_str).name
        if src.exists():
            shutil.copy2(src, path_str)
            restored.append(Path(path_str).name)

    if db_url.startswith("sqlite:"):
        parsed = urlparse(db_url)
        db_path = parsed.path.lstrip("/")
        if db_path:
            dest = (base_dir / db_path).resolve()
            src = latest / dest.name
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored.append(dest.name)
    elif db_url.startswith("postgresql"):
        dump = latest / "postgres_backup.sql"
        if dump.exists():
            print("Note: PostgreSQL dump found:")
            print(dump)
            print("Restore manually with: pg_restore or psql -f")

    if not restored:
        raise FileNotFoundError("Backup did not contain files to restore.")

    print(f"Restored from: {latest}")
    print("Files:", ", ".join(restored))


if __name__ == "__main__":
    main()
