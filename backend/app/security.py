"""Who is calling, and what they may reach. Deny by default: a route is analyst-only unless listed below.

Analyst: HttpOnly SameSite=Strict session cookie (from POST /api/auth/login) or an X-Analyst-Key header for scripts.
Applicant: HttpOnly session cookie from POST /api/session; their jobs are visible to that session only.
Partner: X-Partner-Key header on /api/partner/v1/* (server-to-server from a bank's backend); each partner sees only its
own applications (app/partners.py).
No credential ever lives in a NEXT_PUBLIC_* variable or a URL."""
import hashlib
import hmac
import ipaddress
import re
import secrets
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import (ALLOWED_ORIGINS_RE, ANALYST_KEY, ANALYST_SESSION_TTL_S, ENABLE_DEMO_TOOLS, SESSION_SECRET,
                        TRUST_PROXY, TRUSTED_PROXY_IPS)

ANALYST_COOKIE, APPLICANT_COOKIE = "tid_analyst", "tid_applicant"
APPLICANT_TTL_S = 2 * 3600
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_ORIGIN = re.compile(ALLOWED_ORIGINS_RE + r"$")

PUBLIC = {("GET", "/api/health"), ("GET", "/api/metrics"), ("POST", "/api/session"), ("POST", "/api/auth/login"),
          ("POST", "/api/auth/logout"), ("GET", "/api/auth/me")}
APPLICANT = {("POST", "/api/liveness/challenge"), ("POST", "/api/apply")}
APPLICANT_PREFIX = ("GET", "/api/apply/")
DEMO = {"/api/ring-sim", "/api/testkit", "/api/demo/kit", "/api/attack/live"}
PARTNER_PREFIX = "/api/partner/v1/"


# ------------------------------------------------------------------ signed session tokens
def _mac(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(kind: str, ttl: int) -> tuple[str, str]:
    sid = secrets.token_urlsafe(18)
    payload = f"{kind}.{sid}.{int(time.time()) + ttl}"
    return f"{payload}.{_mac(payload)}", sid


def read_token(token: str | None, kind: str) -> str | None:
    """Session id if the token is ours, of this kind and unexpired."""
    try:
        k, sid, exp, mac = (token or "").split(".")
    except ValueError:
        return None
    payload = f"{k}.{sid}.{exp}"
    if k != kind or not hmac.compare_digest(mac, _mac(payload)) or int(exp) < time.time():
        return None
    return sid


def is_analyst(request: Request) -> bool:
    key = request.headers.get("x-analyst-key")
    if key and hmac.compare_digest(key, ANALYST_KEY):
        return True
    return read_token(request.cookies.get(ANALYST_COOKIE), "analyst") is not None


def analyst_actor(request: Request) -> str:
    """Audit actor taken from the credential, never from the request body."""
    sid = read_token(request.cookies.get(ANALYST_COOKIE), "analyst")
    return f"analyst:{sid[:8]}" if sid else "analyst:api-key"


def applicant_sid(request: Request) -> str | None:
    return read_token(request.cookies.get(APPLICANT_COOKIE), "applicant")


def key_ok(key: str) -> bool:
    return bool(key) and hmac.compare_digest(key, ANALYST_KEY)


def cookie_args(request: Request, ttl: int) -> dict:
    return {"httponly": True, "samesite": "strict", "max_age": ttl, "path": "/",
            "secure": request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"}


# ------------------------------------------------------------------ request facts
def client_ip(request: Request) -> str:
    """The network peer. X-Forwarded-For is believed only when the peer is a configured trusted proxy."""
    peer = request.client.host if request.client else "?"
    if TRUST_PROXY and peer in TRUSTED_PROXY_IPS:
        fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if fwd:
            return fwd
    return peer


def signal_ip(request: Request) -> str | None:
    """IP used as a behaviour/graph signal. Loopback (local demo behind the dev proxy) says nothing about the user."""
    ip = client_ip(request)
    try:
        return None if ipaddress.ip_address(ip).is_loopback else ip
    except ValueError:
        return None


def origin_ok(request: Request) -> bool:
    """CSRF guard for state-changing requests: a browser always sends Origin cross-site; it must be ours."""
    if request.method in SAFE_METHODS:
        return True
    origin = request.headers.get("origin")
    return origin is None or bool(_ORIGIN.match(origin))


def required_role(method: str, path: str) -> str:
    if (method, path) in PUBLIC:
        return "public"
    if (method, path) in APPLICANT or (method == APPLICANT_PREFIX[0] and path.startswith(APPLICANT_PREFIX[1])):
        return "applicant"
    if path in DEMO:
        return "demo"
    if path.startswith(PARTNER_PREFIX):
        return "partner"
    return "analyst"


def allowed(request: Request) -> tuple[bool, int, str]:
    role = required_role(request.method, request.url.path)
    if role == "public":
        return True, 200, ""
    if role == "applicant":
        return (applicant_sid(request) is not None, 401, "start an applicant session first (POST /api/session)")
    if role == "demo" and not ENABLE_DEMO_TOOLS:
        return False, 404, "demo tools are disabled"
    if role == "partner":
        from app.partners import partner_of  # late import: partners imports the app's db and schemas
        return (partner_of(request.headers.get("x-partner-key")) is not None, 401, "missing or invalid X-Partner-Key")
    return (is_analyst(request), 401, "analyst sign-in required")


# ------------------------------------------------------------------ rate limiting
_hits: dict[tuple, deque] = defaultdict(deque)


def rate_ok(bucket: str, who: str, per_min: int) -> bool:
    now, q = time.time(), _hits[(bucket, who)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_min:
        return False
    q.append(now)
    return True
