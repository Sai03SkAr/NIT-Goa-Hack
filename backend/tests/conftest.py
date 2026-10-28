"""Every test runs against an isolated, empty storage root: no real DB, keys, models or uploads are touched."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="trueid-test-")
os.environ.update(TRUEID_MODE="test", TRUEID_DATA_DIR=_TMP, TRUEID_ANALYST_KEY="test-analyst-key",
                  TRUEID_SESSION_SECRET="test-session-secret", TRUEID_HMAC_KEY="test-hmac")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app import db
    from app.main import app
    db.init()
    return TestClient(app)  # no lifespan: no model warm-up, no history replay
