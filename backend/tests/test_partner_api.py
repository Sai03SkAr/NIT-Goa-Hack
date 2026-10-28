"""Partner API + missing-liveness policy. The pipeline is stubbed (no OCR / face models needed):
these tests check wiring, authorisation and decision policy, not model accuracy.
Run from backend/:  ../.venv/bin/python -m pytest tests/test_partner_api.py -q"""
import io
import json
import math

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from app import db, main, partners

NS = partners.PARTNERS["northstar"]["key"]
PL = partners.PARTNERS["paylite"]["key"]
FORM = {"name": "Riya Kamat", "dob": "04/09/1999", "gender": "F", "id_number": "234567890124", "pan": "ABCPK1234Z",
        "phone": "9822001122", "email": "riya.kamat@gmail.com", "address": "MG Road, Margao", "pincode": "403601"}


def _jpg():
    ok, b = cv2.imencode(".jpg", np.full((40, 60, 3), 200, np.uint8))
    return b.tobytes()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db, "engine", eng)
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(main, "UPLOADS", tmp_path)
    seen = {}

    def fake_run(app_id, state):  # stands in for the LangGraph pipeline
        seen[app_id] = state
        with db.session() as s:
            s.add(db.Application(app_id=app_id, ts=state["app"]["ts"], source=state["app"]["source"], name="x",
                                 prob=0.12, band="REVIEW", rule_codes=["BIO_LIVENESS_NOT_PERFORMED"],
                                 fraud_type="incomplete", fraud_label="Verification incomplete", action="Run liveness",
                                 modules=[{"module": "biometric", "risk": 0.2, "reasons": [
                                     {"code": "BIO_LIVENESS_NOT_PERFORMED", "text": "", "weight": 0.25}]}]))
            s.commit()

    monkeypatch.setattr(main, "run_job", fake_run)
    monkeypatch.setattr(main.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    c = TestClient(main.app)
    c.seen = seen
    return c


def _submit(c, key, payload, frames=0):
    files = [("card", ("c.jpg", io.BytesIO(_jpg()), "image/jpeg")), ("selfie", ("s.jpg", io.BytesIO(_jpg()), "image/jpeg"))]
    files += [("frames", (f"f{i}.jpg", io.BytesIO(_jpg()), "image/jpeg")) for i in range(frames)]
    return c.post("/api/partner/v1/applications", data={"payload": json.dumps(payload)}, files=files,
                  headers={"X-Partner-Key": key} if key else {})


def test_rejects_missing_or_wrong_key(client):
    assert _submit(client, None, {"form": FORM}).status_code == 401
    assert _submit(client, "nope", {"form": FORM}).status_code == 401


def test_requires_core_fields(client):
    r = _submit(client, PL, {"form": {**FORM, "email": ""}})
    assert r.status_code == 422 and "email" in r.json()["detail"]


def test_lite_partner_without_frames_is_marked_not_performed(client):
    r = _submit(client, PL, {"form": FORM, "reference": "PL-1", "partner_checks": {"mobile_otp": True},
                             "device": {"ip": "49.36.10.2"}})
    assert r.status_code == 200
    aid = r.json()["application_id"]
    assert aid.startswith("P")
    app = client.seen[aid]["app"]
    assert app["liveness"] == {"performed": False, "passed": False}
    assert app["source"] == "partner:paylite" and app["device"]["ip"] == "49.36.10.2"
    v = client.get(f"/api/partner/v1/applications/{aid}", headers={"X-Partner-Key": PL}).json()
    assert v["status"] == "completed" and v["decision"] == "REVIEW" and v["reference"] == "PL-1"
    assert v["reasons"][0]["text"].startswith("No live selfie check")
    assert v["applicant"]["id_number"].startswith("XXXX")  # masked for the partner console


def test_strict_partner_frames_mean_performed(client):
    aid = _submit(client, NS, {"form": FORM, "liveness": {"passed": True, "challenges": ["blink", "turn_left"]}},
                  frames=3).json()["application_id"]
    st = client.seen[aid]
    assert st["app"]["liveness"]["performed"] is True and len(st["frames"]) == 3


def test_partners_are_isolated(client):
    aid = _submit(client, NS, {"form": FORM}).json()["application_id"]
    assert client.get(f"/api/partner/v1/applications/{aid}", headers={"X-Partner-Key": PL}).status_code == 404
    assert client.get("/api/partner/v1/applications", headers={"X-Partner-Key": PL}).json()["applications"] == []
    assert len(client.get("/api/partner/v1/applications", headers={"X-Partner-Key": NS}).json()["applications"]) == 1


def test_policy_not_performed_is_review_not_injection():
    from app.fusion import fraud_type, model
    from app.modules.biometric import agent as bio
    ext = {"selfie": {"emb": np.ones(4, np.float32) / 2}, "card": {"emb": np.ones(4, np.float32) / 2},
           "passive": {"blur": 100.0, "moire": 10.0}}
    r = bio.assess(ext, np.ones(4, np.float32) / 2, {"performed": False, "passed": False}, [], {})
    codes = [x.code for x in r.reasons]
    assert "BIO_LIVENESS_NOT_PERFORMED" in codes and "BIO_LIVENESS_FAIL" not in codes
    assert math.isnan(r.features["bio_liveness_pass"]) and r.risk < 0.5
    forced, rules = model.hard_rules(r.features)
    assert forced == "REVIEW" and "BIO_LIVENESS_NOT_PERFORMED" in rules
    clean_registry = {"reg_id_found": 1, "reg_name_sim": 1.0, "reg_sim_age_days": 2000, "reg_ckyc": 1}
    assert fraud_type.classify(r.features | clean_registry) == "incomplete"
    # a run challenge that failed is still a failure
    r2 = bio.assess(ext, np.ones(4, np.float32) / 2, {"passed": False}, [], {})
    assert "BIO_LIVENESS_FAIL" in [x.code for x in r2.reasons]
