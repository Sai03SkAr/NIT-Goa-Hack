"""Server-issued liveness challenges. The client never decides liveness: it only returns frames for a challenge the
server picked, bound to the applicant's session, valid once and for CHALLENGE_TTL_S seconds.

shortcut: in-process store, lost on restart and not shared between workers; move to the DB/Redis for multi-worker."""
import random
import secrets
import threading
import time

from app.config import CHALLENGE_TTL_S, PARTNER_CHALLENGE_TTL_S

STEPS = ("turn_left", "turn_right")
VALID, EXPIRED, UNKNOWN, REUSED, WRONG_SESSION = "VALID", "EXPIRED", "UNKNOWN", "REUSED", "WRONG_SESSION"

_lock = threading.Lock()
_open: dict[str, dict] = {}
_used: dict[str, float] = {}  # challenge_id -> consumed at (kept for TTL so a replay reads REUSED, not UNKNOWN)


def _sweep(now: float):
    for k in [k for k, c in _open.items() if now - c["t"] > 2 * c["ttl"]]:
        _open.pop(k, None)
    for k in [k for k, t in _used.items() if now - t > 2 * max(CHALLENGE_TTL_S, PARTNER_CHALLENGE_TTL_S)]:
        _used.pop(k, None)


def issue(session_id: str, ttl: int = CHALLENGE_TTL_S) -> dict:
    """ttl: partners capture the frames mid-journey and submit after later steps (signature, eSign), so they get
    PARTNER_CHALLENGE_TTL_S; the challenge is still one-time, session-bound and server-chosen."""
    now = time.time()
    c = {"challenge_id": secrets.token_urlsafe(16), "sequence": random.sample(STEPS, len(STEPS)),
         "session": session_id, "t": now, "ttl": ttl}
    with _lock:
        _sweep(now)
        _open[c["challenge_id"]] = c
    return {"challenge_id": c["challenge_id"], "sequence": c["sequence"], "expires_in": ttl}


def consume(challenge_id: str | None, session_id: str) -> tuple[dict | None, str]:
    """Atomic one-time use. Returns (challenge, status)."""
    now = time.time()
    with _lock:
        if not challenge_id:
            return None, UNKNOWN
        if challenge_id in _used:
            return None, REUSED
        c = _open.pop(challenge_id, None)
        if c is None:
            return None, UNKNOWN
        _used[challenge_id] = now
    if c["session"] != session_id:
        return None, WRONG_SESSION
    if now - c["t"] > c["ttl"]:
        return None, EXPIRED
    return c, VALID
