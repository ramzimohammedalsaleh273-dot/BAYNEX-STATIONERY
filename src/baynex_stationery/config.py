"""Application configuration and local data paths."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "BAYNEX STATIONERY"
APP_DIR = Path(os.environ.get("BAYNEX_DATA_DIR", Path.home() / ".baynex_stationery"))
DATABASE_PATH = APP_DIR / "baynex_stationery.sqlite3"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
