from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
GEN = DATA / "generated"          # population.json, registry.json, cards/, selfies/
KEYS = DATA / "issuer_keys"
MODELS = ROOT / "models"
PRE = ROOT / "precomputed"
DB_PATH = ROOT / "backend" / "trueid.db"
UPLOADS = ROOT / "backend" / "uploads"

for p in (GEN, KEYS, MODELS, PRE, UPLOADS):
    p.mkdir(parents=True, exist_ok=True)

# Decision bands (configurable from the UI via /api/config)
BANDS = {"approve_below": 0.3, "reject_at": 0.7}

# Face match threshold: overwritten by eval/calibrate_face.py (LFW genuine vs impostor EER)
FACE_THRESHOLD_FILE = MODELS / "face_threshold.json"
DEFAULT_FACE_THRESHOLD = 0.35

# Correlation edge base weights (plan 4.5): IP is low because of CGNAT
EDGE_BASE = {"face": 1.0, "id_hash": 1.0, "device": 0.8, "phone": 0.7, "email_stem": 0.6,
             "address": 0.4, "keystroke": 0.3, "ip": 0.15}

PLACEHOLDERS = {"9999999999", "0000000000", "1234567890", "test@test.com", "na", "n/a", "none", "-", ""}

HMAC_KEY = b"trueid-demo-hmac-key"  # shortcut: hard-coded demo key, load from env/KMS in production
