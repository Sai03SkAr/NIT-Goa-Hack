"""SQLite via SQLModel: applications (masked PII only) + append-only audit log."""
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
    prob: float = 0.0
    band: str = Field(default="REVIEW", index=True)
    forced: str | None = None
    rule_codes: list = Field(default_factory=list, sa_column=Column(JSON))
    fraud_type: str = "none"
    fraud_label: str = ""
    action: str = ""
    modules: list = Field(default_factory=list, sa_column=Column(JSON))
    shap: list = Field(default_factory=list, sa_column=Column(JSON))
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


def audit(s: Session, app_id: str, action: str, note: str = "", actor: str = "system"):
    s.add(AuditLog(app_id=app_id, action=action, note=note, actor=actor))


__all__ = ["Application", "AuditLog", "init", "session", "mask_form", "audit", "select"]
