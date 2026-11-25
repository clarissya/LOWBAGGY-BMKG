import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Supports PostgreSQL via DATABASE_URL (e.g. postgresql+psycopg2://user:pass@localhost:5432/bmkg_qc)
# Falls back to local SQLite file when PostgreSQL is not configured.
DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'bmkg_qc.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

APP_TITLE = "Platform Monitoring Kualitas Data & Tata Kelola Observasi BMKG"
APP_SECRET = os.getenv("BMKG_APP_SECRET", "bmkg-qc-governance-dev-secret-2026")
