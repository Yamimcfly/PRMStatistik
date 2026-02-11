import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config.json"

_config = {}
if CONFIG_PATH.exists():
	try:
		_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
	except Exception:
		_config = {}

def _cfg(path, default=None):
	cur = _config
	for key in path.split("."):
		if not isinstance(cur, dict) or key not in cur:
			return default
		cur = cur[key]
	return cur

DATABASE_URL = _cfg("database.url", os.getenv("DATABASE_URL", "sqlite:///data/prm_stats.sqlite"))
SQLITE_SOURCE_URL = _cfg("database.sqlite_source_url", "sqlite:///data/prm_stats.sqlite")
MIGRATION_OVERWRITE = bool(_cfg("database.migration.overwrite_target", False))
STATION_IATA = _cfg("station_iata", os.getenv("STATION_IATA", "CGN"))

DATA_DIR = Path(_cfg("paths.data_dir", str(BASE_DIR / "data")))
IMPORT_DIR = Path(_cfg("paths.import_dir", str(DATA_DIR)))
EXPORT_DIR = Path(_cfg("paths.export_dir", str(DATA_DIR)))
WCH_MAPPING_FILE = _cfg("paths.wch_mapping_file", "")
DESTINATION_MAPPING_FILE = _cfg("paths.destination_mapping_file", "")
AIRLINE_MAPPING_FILE = _cfg("paths.airline_mapping_file", "")

GUI_SETTINGS = _cfg("gui", {"width": 1100, "height": 700})
FILTER_DEFAULTS = _cfg("filters.default", {})
