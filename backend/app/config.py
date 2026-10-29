"""Settings. Everything is overridable by environment so tests can run against an isolated copy of storage.

Modes:  local_demo (default: demo tools on, but analyst-only)  |  test  |  restricted (secrets must be provided).
Secrets are never predictable: in local_demo/test they are generated once and kept in backend/.secrets/ (git-ignored,
outside every served directory); in restricted mode a missing secret stops startup."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODE = os.getenv("TRUEID_MODE", "local_demo")
if MODE not in ("local_demo", "test", "restricted"):
    raise RuntimeError(f"TRUEID_MODE must be local_demo, test or restricted, not {MODE!r}")

DATA_ROOT = Path(os.getenv("TRUEID_DATA_DIR", str(ROOT)))  # tests point this at a temporary directory
DATA = DATA_ROOT / "data"
GEN = DATA / "generated"          # population.json, registry.json, cards/, selfies/
KEYS = DATA / "issuer_keys"       # issuer private key (generators only) + issuer.pub (verifier)
MODELS = Path(os.getenv("TRUEID_MODELS_DIR", str(DATA_ROOT / "models")))
PRE = Path(os.getenv("TRUEID_PRECOMPUTED_DIR", str(DATA_ROOT / "precomputed")))
BACKEND_DIR = DATA_ROOT / "backend"
DB_PATH = Path(os.getenv("TRUEID_DB_PATH", str(BACKEND_DIR / "trueid.db")))
UPLOADS = BACKEND_DIR / "uploads"
LIVE_HISTORY = BACKEND_DIR / "live_history.jsonl"  # graph records of persisted live applicants, replayed on startup
SECRETS_DIR = BACKEND_DIR / ".secrets"

for p in (GEN, KEYS, MODELS, PRE, UPLOADS, SECRETS_DIR):
    p.mkdir(parents=True, exist_ok=True)


def _secret(name: str, env: str) -> str:
    if os.getenv(env):
        return os.environ[env]
    if MODE == "restricted":
        raise RuntimeError(f"{env} must be set in restricted mode")
    f = SECRETS_DIR / name
    if not f.exists():
        f.write_text(secrets.token_urlsafe(24))
        f.chmod(0o600)
    return f.read_text().strip()


ANALYST_KEY = _secret("analyst_key", "TRUEID_ANALYST_KEY")      # exchanged for an HttpOnly session cookie
SESSION_SECRET = _secret("session_secret", "TRUEID_SESSION_SECRET")
HMAC_KEY = _secret("hmac_key", "TRUEID_HMAC_KEY").encode()        # keyed ID hashes; rotating it re-keys the graph
# shared by consortium members (app/consortium.py), distinct from HMAC_KEY so the internal graph key never leaves TrueID
CONSORTIUM_KEY = _secret("consortium_key", "TRUEID_CONSORTIUM_KEY").encode()

ENABLE_DEMO_TOOLS = os.getenv("TRUEID_ENABLE_DEMO_TOOLS", "false" if MODE == "restricted" else "true") == "true"
TRUST_PROXY = os.getenv("TRUEID_TRUST_PROXY", "false") == "true"
TRUSTED_PROXY_IPS = {ip.strip() for ip in os.getenv("TRUEID_TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",") if ip.strip()}
ALLOWED_ORIGINS_RE = os.getenv("TRUEID_ALLOWED_ORIGINS_RE", r"https?://(localhost|127\.0\.0\.1)(:\d+)?")

# Limits
MAX_UPLOAD_BYTES = int(os.getenv("TRUEID_MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))   # per image
MAX_IMAGE_PIXELS = int(os.getenv("TRUEID_MAX_IMAGE_PIXELS", str(16_000_000)))
MAX_FRAMES = int(os.getenv("TRUEID_MAX_FRAMES", "40"))          # a short head-turn video burst
MAX_PAYLOAD_BYTES = int(os.getenv("TRUEID_MAX_PAYLOAD_BYTES", str(64 * 1024)))
MAX_ACTIVE_JOBS = int(os.getenv("TRUEID_MAX_ACTIVE_JOBS", "4"))
APPLY_RATE_PER_MIN = int(os.getenv("TRUEID_APPLY_RATE", "30"))  # submissions per network peer per minute
RETENTION_DAYS = int(os.getenv("TRUEID_RETENTION_DAYS", "30"))  # uploaded card/selfie images are deleted after this
CHALLENGE_TTL_S = int(os.getenv("TRUEID_CHALLENGE_TTL_S", "180"))
PARTNER_CHALLENGE_TTL_S = int(os.getenv("TRUEID_PARTNER_CHALLENGE_TTL_S", "900"))  # captured mid-journey, submitted after eSign
ANALYST_SESSION_TTL_S = int(os.getenv("TRUEID_ANALYST_SESSION_TTL_S", str(8 * 3600)))
CONSENT_VERSION = "2026-10-consent-v1"
# digital-footprint source (app/modules/footprint/provider.py): "simulated" until a licensed provider is contracted
FOOTPRINT_PROVIDER = os.getenv("TRUEID_FOOTPRINT_PROVIDER", "simulated")

# Decision bands (an analyst can change them; every change is audited)
BANDS = {"approve_below": 0.3, "reject_at": 0.7}
POLICY_VERSION = "policy-v2"      # bump when decision rules change; stale model manifests are refused
FEATURE_SCHEMA_VERSION = "features-v2"

# Face thresholds: written by eval/build_dataset.py from training-split data only
FACE_THRESHOLD_FILE = MODELS / "face_threshold.json"
DEFAULT_FACE_THRESHOLD = 0.35

# Correlation edge base weights (plan 4.5): IP is low because of CGNAT
EDGE_BASE = {"face": 1.0, "id_hash": 1.0, "device": 0.8, "phone": 0.7, "email_stem": 0.6,
             "address": 0.4, "keystroke": 0.3, "ip": 0.15}

PLACEHOLDERS = {"127.0.0.1", "::1", "localhost", "9999999999", "0000000000", "1234567890", "test@test.com", "na", "n/a", "none", "-", ""}
