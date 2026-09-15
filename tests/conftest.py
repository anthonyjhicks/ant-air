"""Test configuration.

The app reads its configuration when ``app.config`` is imported, so the
environment is pinned here, before any test module imports the package.
Tests always run against a throwaway SQLite database, never whatever
``DATABASE_URL`` the developer has set.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_tmp = tempfile.mkdtemp(prefix="ant-air-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["APP_NAME"] = "Ant Air"
os.environ["HOME_CITY"] = "London"
os.environ["HOME_COUNTRY"] = "United Kingdom"
os.environ["HOME_AIRPORTS"] = "LHR,LGW,LCY"
os.environ["DEFAULT_TRAVELLER"] = "Sam Rivers"
for key in ("FLIGHTAWARE_API_KEY", "GEMINI_API_KEY", "N8N_WEBHOOK_TOKEN"):
    os.environ.pop(key, None)
