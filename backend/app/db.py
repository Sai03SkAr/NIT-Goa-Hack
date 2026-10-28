"""SQLite via SQLModel: applications (masked PII only) + append-only, hash-chained audit log."""
import hashlib
import json
import threading
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import DB_PATH

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Application(SQLModel, table=True):
    app_id: str = Field(primary_key=True)
    ts: str = Field(index=True)              # ISO-8601, sorts lexically
    source: str = "seed"                       # seed | live | ring_sim
    name: str = ""
    id_last4: str = ""
    form_masked: dict = Field(default_factory=dict, sa_column=Column(JSON))
    prob: float | None = None                  # calibrated model probability; None when the model was unavailable
    band: str = Field(default="REVIEW", index=True)
    forced: str | None = None
    rule_codes: list = Field(default_factory=list, sa_column=Column(JSON))
    fraud_type: str = "none"
    fraud_label: str = ""
    action: str = ""
    modules: list = Field(default_factory=list, sa_column=Column(JSON))
    shap: list = Field(default_factory=list, sa_column=Column(JSON))
    evidence: list = Field(default_factory=list, sa_column=Column(JSON))   # policy check statuses
    model_status: str = ""
    policy_version: str = ""
    step_up: dict = Field(default_factory=dict, sa_column=Column(JSON))    # simulated, display only
    summary: str = ""
    stepped_up: bool = False
    status: str = "open"                       # open | approved | rejected (analyst)
    card_path: str = ""
    selfie_path: str = ""
    truth_label: int | None = None             # seeded data only, for the metrics page
    truth_type: str | None = None


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    app_id: str = Field(index=True)
    ts: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    actor: str = "system"
    action: str = ""
    note: str = ""
    prev_hash: str = ""
    hash: str = ""              # sha256(prev_hash + this entry): editing or deleting any row breaks the chain


def init():
    SQLModel.metadata.create_all(engine)


def session() -> Session:
    return Session(engine)


def mask_form(form: dict) -> dict:
    m = dict(form)
    m["id_number"] = "XXXX XXXX " + form.get("id_number", "")[-4:]
    if form.get("pan"):
        m["pan"] = form["pan"][:2] + "XXXXX" + form["pan"][-3:]
    if form.get("phone"):
        m["phone"] = "XXXXXX" + form["phone"][-4:]
    return m


_audit_lock = threading.Lock()


def _entry_hash(prev: str, e: AuditLog) -> str:
    body = json.dumps([e.app_id, e.ts, e.actor, e.action, e.note], ensure_ascii=False)
    return hashlib.sha256((prev + body).encode()).hexdigest()


def audit(_s: Session | None, app_id: str, action: str, note: str = "", actor: str = "system"):
    """Appends one chained entry in its own transaction (so concurrent writers cannot fork the chain).
    The caller's session is accepted for call-site compatibility; the entry does not wait for its commit."""
    with _audit_lock, Session(engine) as s:
        last = s.exec(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
        e = AuditLog(app_id=app_id, action=action, note=note, actor=actor, prev_hash=last.hash if last else "")
        e.hash = _entry_hash(e.prev_hash, e)
        s.add(e)
        s.commit()


def verify_audit() -> dict:
    """Walk the chain; report the first entry whose content or link no longer matches."""
    prev, n = "", 0
    with Session(engine) as s:
        for e in s.exec(select(AuditLog).order_by(AuditLog.id)):
            n += 1
            if e.prev_hash != prev or e.hash != _entry_hash(prev, e):
                return {"ok": False, "entries": n, "first_bad_id": e.id}
            prev = e.hash
    return {"ok": True, "entries": n, "head": prev[:16]}


__all__ = ["Application", "AuditLog", "init", "session", "mask_form", "audit", "select"]
