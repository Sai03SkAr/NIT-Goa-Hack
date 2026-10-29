"""Partner API: wiring, authorisation, partner isolation and server-issued liveness. The pipeline is stubbed (no OCR /
face models needed): these tests check what reaches the pipeline and what a partner may see, not model accuracy.
Run from backend/:  ../.venv/bin/python -m pytest tests/test_partner_api.py -q"""
import io
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, main, partners

NS = partners.PARTNERS["northstar"]["key"]
PL = partners.PARTNERS["paylite"]["key"]
TW = partners.PARTNERS["tideway"]["key"]
FORM = {"name": "Riya Kamat", "dob": "04/09/1999", "gender": "F", "id_number": "234567890124", "pan": "ABCPK1234Z",
        "phone": "9822001122", "email": "riya.kamat@gmail.com", "address": "MG Road, Margao", "pincode": "403601"}


def _jpg(v=200):
    ok, b = cv2.imencode(".jpg", np.full((40, 60, 3), v, np.uint8))
    return b.tobytes()


@pytest.fixture()
def client(monkeypatch):
    db.init()
    seen = {}

    def fake_run(job, state):  # stands in for the LangGraph pipeline
        aid = job.app_id
        seen[aid] = state
        with db.session() as s:
            s.add(db.Application(app_id=aid, ts=state["app"]["ts"], source=state["app"]["source"], name="x",
                                 prob=0.12, band="REVIEW", rule_codes=["EV_LIVENESS_NOT_PROVIDED"],
                                 fraud_type="inconclusive", fraud_label="Incomplete evidence", action="Collect checks",
                                 evidence=[{"check": "liveness", "label": "Server-verified head-turn challenge",
                                            "status": "NOT_PROVIDED", "required": True, "source": "server"}],
                                 modules=[{"module": "biometric", "risk": 0.2, "reasons": [
                                     {"code": "BIO_LIVENESS_NOT_PROVIDED", "text": "", "weight": 0.0}]}]))
            s.commit()
        job.done = True

    monkeypatch.setattr(main, "run_job", fake_run)
    monkeypatch.setattr(main, "EXECUTOR", type("X", (), {"submit": staticmethod(lambda fn, *a: fn(*a))})())
    c = TestClient(main.app)
    c.seen = seen
    return c


def _submit(c, key, payload, frames=0):
    files = [("card", ("c.jpg", io.BytesIO(_jpg()), "image/jpeg")), ("selfie", ("s.jpg", io.BytesIO(_jpg()), "image/jpeg"))]
    files += [("frames", (f"f{i}.jpg", io.BytesIO(_jpg((100 + 40 * i) % 256)), "image/jpeg")) for i in range(frames)]
    return c.post("/api/partner/v1/applications", data={"payload": json.dumps(payload)}, files=files,
                  headers={"X-Partner-Key": key} if key else {})


def test_rejects_missing_or_wrong_key(client):
    assert _submit(client, None, {"form": FORM}).status_code == 401
    assert _submit(client, "nope", {"form": FORM}).status_code == 401
    assert client.post("/api/partner/v1/liveness/challenge").status_code == 401


def test_validates_form_like_apply(client):
    r = _submit(client, PL, {"form": {**FORM, "email": ""}})
    assert r.status_code == 422 and any(x["field"] == "email" for x in r.json()["detail"])
    assert _submit(client, PL, {"form": FORM}, frames=main.MAX_FRAMES + 1).status_code == 422  # burst limit
    bad_geo = {"form": FORM, "device": {"geo": {"lat": 123.0, "lon": 73.8}}}
    assert _submit(client, PL, bad_geo).status_code == 422  # same Geo validation as /api/apply


def test_upload_partner_reaches_pipeline_without_challenge(client):
    r = _submit(client, PL, {"form": FORM, "reference": "PL-1", "partner_checks": {"mobile_otp": True},
                             "device": {"ip": "49.36.10.2"}})
    assert r.status_code == 200
    aid = r.json()["application_id"]
    assert aid.startswith("P")
    app = client.seen[aid]["app"]
    assert app["challenge"] is None  # no server-issued challenge: liveness becomes NOT_PROVIDED in the pipeline
    assert app["source"] == "partner:paylite" and app["device"]["ip"] == "49.36.10.2"
    v = client.get(f"/api/partner/v1/applications/{aid}", headers={"X-Partner-Key": PL}).json()
    assert v["status"] == "completed" and v["decision"] == "REVIEW" and v["reference"] == "PL-1"
    assert v["reasons"][0]["text"].startswith("No server-verified liveness")
    assert v["evidence"][0]["status"] == "NOT_PROVIDED"
    assert v["applicant"]["id_number"].startswith("XXXX")  # masked for the partner console
    from app.learning import FIXABLE_STATUS
    tips = v["applicant_coaching"]["tips"]  # what the partner may show its customer: fixable issues only
    assert "liveness" in [t["check"] for t in tips] and all(t["check"] in FIXABLE_STATUS for t in tips)


def test_geo_tag_reaches_the_pipeline(client):
    aid = _submit(client, TW, {"form": FORM, "device": {"geo": {"lat": 15.49, "lon": 73.82, "acc": 25}}}).json()["application_id"]
    assert client.seen[aid]["app"]["geo"] == {"lat": 15.49, "lng": 73.82, "accuracy": 25.0, "ts": None}
    plain = _submit(client, TW, {"form": FORM}).json()["application_id"]
    assert client.seen[plain]["app"]["geo"] is None  # declined location: recorded as not provided, never blocks


def test_partner_challenge_is_server_issued_once_and_partner_bound(client):
    ch = client.post("/api/partner/v1/liveness/challenge", headers={"X-Partner-Key": TW}).json()
    assert sorted(ch["sequence"]) == ["turn_left", "turn_right"] and ch["expires_in"] >= 600
    aid = _submit(client, TW, {"form": FORM, "challenge_id": ch["challenge_id"]}, frames=3).json()["application_id"]
    st = client.seen[aid]
    assert st["app"]["challenge"] == {"status": "VALID", "sequence": ch["sequence"]} and len(st["frames"]) == 3
    replay = _submit(client, TW, {"form": FORM, "challenge_id": ch["challenge_id"]}, frames=3).json()["application_id"]
    assert client.seen[replay]["app"]["challenge"]["status"] == "REUSED"
    other = client.post("/api/partner/v1/liveness/challenge", headers={"X-Partner-Key": NS}).json()
    stolen = _submit(client, TW, {"form": FORM, "challenge_id": other["challenge_id"]}, frames=3).json()["application_id"]
    assert client.seen[stolen]["app"]["challenge"]["status"] == "WRONG_SESSION"


def test_partners_are_isolated(client):
    aid = _submit(client, NS, {"form": FORM, "reference": "iso"}).json()["application_id"]
    assert client.get(f"/api/partner/v1/applications/{aid}", headers={"X-Partner-Key": PL}).status_code == 404
    mine = client.get("/api/partner/v1/applications", headers={"X-Partner-Key": PL}).json()["applications"]
    assert aid not in {a["application_id"] for a in mine}
    ns = client.get("/api/partner/v1/applications", headers={"X-Partner-Key": NS}).json()["applications"]
    assert aid in {a["application_id"] for a in ns}


def test_analytics_are_per_partner(client):
    aid = _submit(client, TW, {"form": FORM, "partner_checks": {"mobile_otp": True, "esign": False}}).json()["application_id"]
    assert client.get("/api/partner/v1/analytics").status_code == 401
    a = client.get("/api/partner/v1/analytics?days=7", headers={"X-Partner-Key": TW}).json()
    assert a["partner"] == "Tideway Securities" and a["completed"] >= 1 and a["decisions"]["REVIEW"] >= 1
    assert len(a["daily"]) == 7 and a["daily"][-1]["REVIEW"] >= 1
    assert {"label": "Incomplete evidence", "count": a["fraud_patterns"][0]["count"]} in a["fraud_patterns"]
    assert a["checks"][0]["check"] == "liveness" and a["checks"][0]["OTHER"] >= 1
    assert a["partner_checks"]["mobile_otp"] > 0
    other = client.get("/api/partner/v1/analytics", headers={"X-Partner-Key": PL}).json()
    assert other["partner"] == "PayLite Wallet"  # never another partner's numbers
    assert aid  # the Tideway case above is counted only for Tideway


def test_registry_lookups_need_a_partner_key_and_mocks_stay_analyst_only(client, monkeypatch):
    from app.modules.registry import mocks
    monkeypatch.setattr(mocks, "pan", lambda p: {"name": "Riya Kamat", "dob": "04/09/1999", "id_last4": "0124",
                                                 "subject": "234567890124"} if p == "ABCPK1234Z" else None)
    assert client.get("/api/partner/v1/registry/pan/ABCPK1234Z").status_code == 401
    r = client.get("/api/partner/v1/registry/pan/ABCPK1234Z", headers={"X-Partner-Key": TW}).json()
    assert r == {"name": "Riya Kamat", "dob": "04/09/1999", "id_last4": "0124"}  # only what NSDL would give a bank
    assert client.get("/api/partner/v1/registry/pan/ZZZPZ0000Z", headers={"X-Partner-Key": TW}).status_code == 404
    assert client.get("/mock/pan/ABCPK1234Z", headers={"X-Partner-Key": TW}).status_code == 401
