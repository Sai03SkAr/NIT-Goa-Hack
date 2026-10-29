"""Cross-institution shared fraud graph (consortium), privacy-preserving.

Banks don't share customer data with each other. Each member turns an applicant's identifiers into keyed hashes
(HMAC-SHA256 with the consortium key) before anything leaves it, so the shared store holds tokens, never PII:
ID number, PAN, phone, email, device, bank account, and the normalised name. Matching tokens across institutions
reveal what one bank cannot see alone:

  - the same ID number or PAN used under a DIFFERENT name at another institution   (synthetic / Frankenstein identity)
  - an identifier that another institution REJECTED                                  (known fraud re-used elsewhere)
  - one device onboarding several different people across institutions this week     (mule recruitment / ring)

Answers carry counts only: never the other institution, its applicant's name or anything else it submitted.
An alert can only hold a case for review (policy.decide), never approve or auto-reject it on its own.

TrueID is itself a member: every application it decides is checked and then recorded (pipeline.fusion_node /
persist_node), tagged with the partner it came from. Banks that don't use TrueID's pipeline join through
/api/partner/v1/consortium/* and hash locally (scripts/consortium_client.py).

shortcut: members hold the shared HMAC key, so a member could brute-force low-entropy identifiers (a 10-digit phone)
offline. Production would use an oblivious PRF or private set intersection so no member ever holds the key."""
import hashlib
import hmac
import re
from datetime import datetime, timedelta

from sqlmodel import Field, SQLModel, select

from app import db
from app import policy as P
from app.config import CONSORTIUM_KEY
from app.modules.correlation.fuzzy import tokens as name_tokens

KINDS = ("id_number", "pan", "phone", "email", "device", "account")
WINDOW_DAYS = 180            # how far back alerts look
DEVICE_WINDOW_DAYS = 7       # mule herding window
DEVICE_PEOPLE = 2            # other people on the same device at other institutions -> alert


class ConsortiumSignal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    institution: str = Field(index=True)
    kind: str = Field(index=True)
    token: str = Field(index=True)
    name_token: str = ""
    outcome: str = ""             # APPROVE | REVIEW | REJECT ("" until decided)
    ref: str = Field(default="", index=True)   # the member's own opaque reference (hashed, for updates)
    ts: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"), index=True)


def _norm(kind: str, v) -> str:
    s = str(v or "").strip()
    if kind in ("id_number", "account"):
        return re.sub(r"\D", "", s)
    if kind == "phone":
        return re.sub(r"\D", "", s)[-10:]
    if kind in ("pan",):
        return s.upper().replace(" ", "")
    if kind == "email":
        return s.lower()
    return s


def token(kind: str, value, key: bytes | None = None) -> str:
    """What a member computes locally. Empty value -> empty token (not shared)."""
    n = _norm(kind, value) if kind != "name" else " ".join(sorted(name_tokens(value)))
    if not n:
        return ""
    return hmac.new(key or CONSORTIUM_KEY, f"{kind}:{n}".encode(), hashlib.sha256).hexdigest()[:40]


def tokens_for(app: dict) -> tuple[dict, str]:
    """Tokens for an application TrueID itself processed (it already holds the raw values)."""
    f, d = app.get("form", {}), app.get("device", {})
    raw = {"id_number": f.get("id_number"), "pan": f.get("pan"), "phone": f.get("phone"), "email": f.get("email"),
           "device": d.get("device_id"), "account": f.get("account_no")}
    return {k: t for k, v in raw.items() if (t := token(k, v))}, token("name", f.get("name"))


def institution_of(app: dict) -> str:
    src = app.get("source", "live")
    return src.split(":", 1)[1] if src.startswith("partner:") else "trueid"


def check(institution: str, toks: dict, name_token: str, now: datetime | None = None) -> dict:
    """Matches from OTHER institutions. Returns {status, alerts[{code, kind, institutions, text}], seen_elsewhere}."""
    now = now or datetime.now()
    since = (now - timedelta(days=WINDOW_DAYS)).isoformat(timespec="seconds")
    dev_since = (now - timedelta(days=DEVICE_WINDOW_DAYS)).isoformat(timespec="seconds")
    alerts, seen = [], {}
    with db.session() as s:
        for kind, t in toks.items():
            if kind not in KINDS or not t:
                continue
            rows = s.exec(select(ConsortiumSignal).where(ConsortiumSignal.kind == kind, ConsortiumSignal.token == t,
                                                         ConsortiumSignal.institution != institution,
                                                         ConsortiumSignal.ts >= since)).all()
            if not rows:
                continue
            inst = {r.institution for r in rows}
            seen[kind] = len(inst)
            other_names = {r.name_token for r in rows if r.name_token and name_token and r.name_token != name_token}
            if kind in ("id_number", "pan") and other_names:
                alerts.append({"code": "COR_NET_ID_OTHER_NAME", "kind": kind, "institutions": len({r.institution for r in rows if r.name_token in other_names})})
            if any(r.outcome == "REJECT" for r in rows):
                alerts.append({"code": "COR_NET_PRIOR_REJECT", "kind": kind, "institutions": len({r.institution for r in rows if r.outcome == "REJECT"})})
            if kind == "device":
                people = {r.name_token for r in rows if r.ts >= dev_since and r.name_token and r.name_token != name_token}
                if len(people) >= DEVICE_PEOPLE:
                    alerts.append({"code": "COR_NET_DEVICE_MANY", "kind": kind, "institutions": len(inst), "people": len(people)})
    if not toks:
        status = P.NOT_PROVIDED
    else:
        status = P.FAIL if alerts else P.PASS
    return {"status": status, "alerts": alerts, "seen_elsewhere": seen}


def record(institution: str, toks: dict, name_token: str, outcome: str = "", ref: str = ""):
    """Store (or update the outcome of) this application's tokens."""
    ref_h = hashlib.sha256(f"{institution}:{ref}".encode()).hexdigest()[:24] if ref else ""
    with db.session() as s:
        if ref_h:
            old = s.exec(select(ConsortiumSignal).where(ConsortiumSignal.institution == institution,
                                                        ConsortiumSignal.ref == ref_h)).all()
            if old:
                for r in old:
                    r.outcome = outcome or r.outcome
                    s.add(r)
                s.commit()
                return
        for kind, t in toks.items():
            if kind in KINDS and t:
                s.add(ConsortiumSignal(institution=institution, kind=kind, token=t, name_token=name_token,
                                       outcome=outcome, ref=ref_h))
        s.commit()


def stats() -> dict:
    with db.session() as s:
        rows = s.exec(select(ConsortiumSignal)).all()
    return {"members": len({r.institution for r in rows}), "signals": len(rows),
            "rejected_signals": sum(r.outcome == "REJECT" for r in rows)}
