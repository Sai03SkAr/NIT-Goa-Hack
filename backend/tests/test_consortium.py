"""Cross-institution fraud network: hashed identifiers only, alerts across institutions, counts-only answers, and a
policy that can hold a case for review but never approve or reject it on this signal alone."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import consortium as C
from app import db, main, partners, policy as P

KH = partners.PARTNERS["kestrel"]["key"]
TW = partners.PARTNERS["tideway"]["key"]


@pytest.fixture(autouse=True)
def _db():
    db.init()


def uid() -> str:
    """A fresh 12-digit ID per test, so tests sharing the session database don't see each other."""
    return str(uuid.uuid4().int)[:12]


def toks(**kv):
    return {k: C.token(k, v) for k, v in kv.items()}


def test_tokens_normalise_and_depend_on_the_key():
    assert C.token("id_number", "2345 6789 0124") == C.token("id_number", "234567890124")
    assert C.token("phone", "+91 98220 01122") == C.token("phone", "9822001122")
    assert C.token("name", "Riya Kamat") == C.token("name", "KAMAT RIYA")       # order-free, case-free
    assert C.token("id_number", "234567890124", key=b"other") != C.token("id_number", "234567890124")
    assert len(C.token("pan", "ABCPK1234Z")) == 40 and C.token("pan", "") == ""


def test_same_id_under_another_name_at_another_bank():
    idn = uid()
    C.record("kestrel", toks(id_number=idn), C.token("name", "Riya Kamat"), outcome="APPROVE", ref="k1-" + idn)
    other = C.check("tideway", toks(id_number=idn), C.token("name", "Arjun Naik"))
    assert other["status"] == P.FAIL and other["alerts"][0]["code"] == "COR_NET_ID_OTHER_NAME"
    same = C.check("tideway", toks(id_number=idn), C.token("name", "Riya Kamat"))
    assert same["status"] == P.PASS and same["seen_elsewhere"] == {"id_number": 1}   # banking at two places is normal
    own = C.check("kestrel", toks(id_number=idn), C.token("name", "Arjun Naik"))
    assert own["status"] == P.PASS  # a member's own history is handled by its own graph, not the network


def test_identifier_rejected_elsewhere():
    phone = "9" + uid()[:9]
    C.record("meridian", toks(phone=phone), C.token("name", "Mule One"), outcome="REJECT", ref="m-" + phone)
    r = C.check("kestrel", toks(phone=phone), C.token("name", "Mule One"))
    assert [a["code"] for a in r["alerts"]] == ["COR_NET_PRIOR_REJECT"]


def test_one_device_onboarding_many_people_across_banks():
    dev = "D" + uid()
    C.record("tideway", toks(device=dev), C.token("name", "Person One"), outcome="REVIEW", ref="t-" + dev)
    C.record("meridian", toks(device=dev), C.token("name", "Person Two"), outcome="REVIEW", ref="m-" + dev)
    r = C.check("kestrel", toks(device=dev), C.token("name", "Person Three"))
    assert any(a["code"] == "COR_NET_DEVICE_MANY" and a["people"] == 2 for a in r["alerts"])


def test_outcome_update_by_reference():
    idn = uid()
    C.record("tideway", toks(id_number=idn), C.token("name", "Riya Kamat"), ref="case-" + idn)
    assert C.check("kestrel", toks(id_number=idn), C.token("name", "Riya Kamat"))["status"] == P.PASS
    C.record("tideway", {}, "", outcome="REJECT", ref="case-" + idn)  # later decided as fraud
    assert C.check("kestrel", toks(id_number=idn), C.token("name", "Riya Kamat"))["alerts"][0]["code"] == "COR_NET_PRIOR_REJECT"


def test_policy_holds_but_never_decides_on_the_network_alone():
    ok = {"status": "ok", "prob": 0.01}
    passing = {f"ev_{c}": P.CODE[P.PASS] for c in P.REQUIRED}  # same passing case as tests/test_policy.py
    passing.update(bio_blur=100.0, doc_ocr_conf=0.95, bio_media_reuse=0.0, cor_device_people_7d=0.0)
    assert P.decide(passing, ok)["band"] == "APPROVE"
    held = P.decide({**passing, "ev_network": P.CODE[P.FAIL]}, ok)
    assert held["band"] == "REVIEW" and "EV_NETWORK_FAIL" in held["rule_codes"] and not held["approval_eligible"]
    assert P.decide({**passing, "ev_network": P.CODE[P.PASS]}, ok)["band"] == "APPROVE"
    assert P.decide({**passing, "ev_network": P.CODE[P.FAIL]}, {"status": "ok", "prob": 0.95})["band"] == "REJECT"  # model, not network


def test_pipeline_network_module():
    from app.graph.pipeline import network_module
    idn = uid()
    C.record("meridian", toks(id_number=idn), C.token("name", "Riya Kamat"), outcome="APPROVE", ref="m-" + idn)
    app = {"source": "partner:kestrel", "form": {"id_number": idn, "name": "Arjun Naik"}, "device": {}}
    m = network_module(app)
    assert m["module"] == "network" and m["features"]["ev_network"] == P.CODE[P.FAIL]
    assert m["reasons"][0]["code"] == "COR_NET_ID_OTHER_NAME"
    assert "Riya" not in str(m) and "meridian" not in str(m)  # counts only: no other bank, no other name


def test_member_api_takes_tokens_only():
    c = TestClient(main.app)
    idn = uid()
    body = {"tokens": toks(id_number=idn, pan="ABCPK1234Z"), "name_token": C.token("name", "Riya Kamat"),
            "outcome": "REJECT", "ref": "x-" + idn}
    assert c.post("/api/partner/v1/consortium/report", json=body).status_code == 401
    assert c.post("/api/partner/v1/consortium/report", json=body, headers={"X-Partner-Key": TW}).json() == {"recorded": True}
    r = c.post("/api/partner/v1/consortium/check", json={"tokens": body["tokens"], "name_token": C.token("name", "Arjun Naik")},
               headers={"X-Partner-Key": KH}).json()
    assert {a["code"] for a in r["alerts"]} == {"COR_NET_ID_OTHER_NAME", "COR_NET_PRIOR_REJECT"}
    assert "tideway" not in str(r).lower()
    raw = c.post("/api/partner/v1/consortium/check", json={"tokens": {"id_number": idn}}, headers={"X-Partner-Key": KH})
    assert raw.status_code == 422  # raw identifiers are refused: members must hash locally
    assert c.get("/api/partner/v1/consortium/stats", headers={"X-Partner-Key": KH}).json()["members"] >= 2


def test_reference_client_hashes_exactly_like_the_server():
    """scripts/consortium_client.py is what member banks run; its tokens must match TrueID's or nothing ever matches."""
    import importlib.util
    from pathlib import Path
    from app.config import CONSORTIUM_KEY
    spec = importlib.util.spec_from_file_location("cc", Path(__file__).resolve().parents[2] / "scripts/consortium_client.py")
    cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
    for kind, v in [("id_number", "2345 6789 0124"), ("pan", "abcpk1234z"), ("phone", "+91 98220 01122"),
                    ("email", "Riya.Kamat@Example.com"), ("device", "D1a2b3c4d5"), ("account", "4002-1187-650"),
                    ("name", "Mohd Shaikh"), ("name", "riya  kamat")]:
        assert cc.token(kind, v, CONSORTIUM_KEY) == C.token(kind, v), (kind, v)


def test_erasure_also_removes_the_applications_network_signals(client):
    """DPDP right to erasure: deleting an applicant must take back what they contributed to the network."""
    from app import consortium, db
    toks = {"id_number": "a" * 40, "phone": "b" * 40}
    consortium.record("trueid", toks, "c" * 40, outcome="REVIEW", ref="LERASE001")
    with db.session() as s:
        s.add(db.Application(app_id="LERASE001", ts="2026-10-29T10:00:00", source="live", name="Erase Me"))
        s.commit()
    assert consortium.check("kestrel", toks, "d" * 40)["seen_elsewhere"]
    r = client.delete("/api/apps/LERASE001", headers={"X-Analyst-Key": "test-analyst-key"})
    assert r.status_code == 200
    assert not consortium.check("kestrel", toks, "d" * 40)["seen_elsewhere"]
