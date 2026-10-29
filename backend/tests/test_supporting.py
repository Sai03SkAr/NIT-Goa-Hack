"""Supporting-document checks (bill, salary slip, statement, cheque) and the partner endpoints around them.
OCR is stubbed: these tests check matching, re-use and integrity logic, not EasyOCR."""
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import db, main, partners
from app.modules.document import supporting as SD

KH = partners.PARTNERS["kestrel"]["key"]
H = {"X-Partner-Key": KH}
BILL = ("GOA ELECTRICITY DEPARTMENT CONSUMER NO 6102 3345 7781 BILL DATE 02/10/2026 NAME RIYA KAMAT "
        "14 ALTINHO ROAD PANAJI 403001 AMOUNT PAYABLE 1,240.00")


def _jpg(seed=1, comment: bytes | None = None) -> bytes:
    rng = np.random.default_rng(seed)
    img = (rng.random((640, 900, 3)) * 255).astype(np.uint8)  # noisy = sharp enough to pass the legibility check
    b = io.BytesIO()
    Image.fromarray(img).save(b, "JPEG", **({"comment": comment} if comment else {}))
    return b.getvalue()


@pytest.fixture()
def client(monkeypatch):
    db.init()
    monkeypatch.setattr(SD, "page_text", lambda img: BILL)
    return TestClient(main.app)


def _check(c, kind, claims, owner, raw):
    import json
    return c.post("/api/partner/v1/documents/check", headers=H, files={"file": ("d.jpg", io.BytesIO(raw), "image/jpeg")},
                  data={"kind": kind, "claims": json.dumps(claims), "owner": owner})


def _status(r, check):
    return next(x["status"] for x in r["checks"] if x["check"] == check)


def test_found_matches_how_documents_print_values():
    assert SD.found("name", "Riya Kamat", BILL) and SD.found("name", "R Kamat", BILL)
    assert not SD.found("name", "Rohit Kamat", BILL)
    assert SD.found("digits", "610233457781", BILL) and not SD.found("digits", "610233450000", BILL)
    assert SD.found("date", "2026-10-02", BILL) and not SD.found("date", "2026-09-02", BILL)
    assert SD.found("amount", "1240", BILL) and not SD.found("amount", "124", BILL)


def test_bill_claims_are_checked_against_the_page(client):
    r = _check(client, "electricity_bill", {"name": "Riya Kamat", "consumer_no": "6102 3345 7781", "bill_date": "2026-10-02",
                                            "pincode": "403002"}, "Riya Kamat", _jpg(11)).json()
    assert _status(r, "legible") == "PASS" and _status(r, "ai_marker") == "PASS" and _status(r, "reuse") == "PASS"
    assert _status(r, "text_name") == "PASS" and _status(r, "text_consumer_no") == "PASS"
    assert _status(r, "text_bill_date") == "PASS" and _status(r, "text_pincode") == "FAIL"  # 403002 is not printed


def test_same_bill_for_another_applicant_is_flagged(client):
    raw = _jpg(12)
    assert _status(_check(client, "electricity_bill", {}, "Riya Kamat", raw).json(), "reuse") == "PASS"
    assert _status(_check(client, "electricity_bill", {}, "Riya Kamat", raw).json(), "reuse") == "PASS"  # same person
    assert _status(_check(client, "electricity_bill", {}, "Arjun Naik", raw).json(), "reuse") == "FAIL"


def test_ai_generator_marker_fails(client):
    r = _check(client, "salary_slip", {}, "Riya Kamat", _jpg(13, b"trainedAlgorithmicMedia")).json()
    assert _status(r, "ai_marker") == "FAIL"


def test_ocr_unavailable_is_never_a_pass(client, monkeypatch):
    monkeypatch.setattr(SD, "page_text", lambda img: None)
    r = _check(client, "cheque", {"name": "Riya Kamat"}, "Riya Kamat", _jpg(14)).json()
    assert _status(r, "text_name") == "UNAVAILABLE"


def test_document_endpoint_auth_and_kind(client):
    assert client.post("/api/partner/v1/documents/check", data={"kind": "cheque"}).status_code == 401
    assert _check(client, "passport_scan", {}, "x", _jpg(15)).status_code == 422


def test_pan_link_status(client, monkeypatch):
    from app.modules.registry import mocks
    monkeypatch.setattr(mocks, "pan", lambda p: {"name": "Riya Kamat", "dob": "04/09/1999", "subject": "234567890124"}
                        if p == "ABCPK1234Z" else None)
    q = lambda pan, idn: client.get(f"/api/partner/v1/registry/pan-link?pan={pan}&id_number={idn}", headers=H).json()  # noqa: E731
    assert q("ABCPK1234Z", "234567890124") == {"pan_found": True, "linked": True}
    assert q("ABCPK1234Z", "345678901238")["linked"] is False
    assert q("ZZZPZ0000Z", "234567890124") == {"pan_found": False, "linked": False}
    assert client.get("/api/partner/v1/registry/pan/ABCPK1234Z", headers=H).json()["id_last4"] == "0124"


def test_id_card_qr_checks_run_without_ocr(monkeypatch):
    """Signature and 'card belongs to this person' come from the signed QR alone; QR-vs-print waits for OCR."""
    import cv2
    from app.modules.document import card, qr_sign
    db.init()
    monkeypatch.setattr(SD.CARD_OCR, "get", lambda wait=2.0: None)
    f = {"n": "RIYA KAMAT", "d": "04/09/1999", "g": "F", "id": "234567890124", "i": "15/03/2019"}
    img = card.render({"name": f["n"], "dob": f["d"], "gender": "F", "id_number": f["id"], "issue_date": f["i"]}, None, qr_sign.make_qr_text(f))
    b = io.BytesIO(); img.save(b, "PNG"); raw = b.getvalue()
    bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    form = {"name": "Riya Kamat", "dob": "04/09/1999", "id_number": "234567890124", "pan": ""}
    st = lambda r, k: next(c["status"] for c in r["checks"] if c["check"] == k)  # noqa: E731
    r = SD.check_id_card(raw, bgr, form, "riya kamat", "kestrel")
    assert st(r, "doc_signature") == "PASS" and st(r, "form_consistency") == "PASS" and st(r, "doc_consistency") == "UNAVAILABLE"
    r2 = SD.check_id_card(raw, bgr, {**form, "name": "Arjun Naik", "id_number": "345678901238"}, "arjun naik", "kestrel")
    assert st(r2, "form_consistency") == "FAIL" and st(r2, "reuse") == "FAIL"  # someone else's card, already used by Riya


def test_same_template_different_person_is_not_reuse(client):
    """Bills from one provider share a mostly-white template; only the same image may count as re-use."""
    from PIL import ImageDraw, ImageFont

    def bill(name):
        img = Image.new("RGB", (1240, 1600), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 1240, 120], fill=(15, 118, 110))
        for i, line in enumerate([f"Consumer Name  {name}", "Bill Date  02/10/2026", "Amount  1,240.00"]):
            d.text((60, 220 + 48 * i), line, fill="black", font=ImageFont.load_default(32))
        b = io.BytesIO(); img.save(b, "JPEG", quality=90)
        return b.getvalue()

    assert _status(_check(client, "electricity_bill", {}, "Meera Desai", bill("MEERA DESAI")).json(), "reuse") == "PASS"
    assert _status(_check(client, "electricity_bill", {}, "Karthik Prabhu", bill("KARTHIK PRABHU")).json(), "reuse") == "PASS"


def test_an_older_database_gains_new_columns_on_startup(tmp_path):
    """A DB created before a column existed must keep working after a pull (additive migration in db.init)."""
    import sqlite3
    from sqlalchemy import create_engine, inspect
    from app import db
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE application (app_id VARCHAR PRIMARY KEY, ts VARCHAR, name VARCHAR)")
    con.execute("INSERT INTO application VALUES ('OLD1', '2026-01-01T00:00:00', 'Old Row')")
    con.commit(); con.close()
    old = db.engine
    db.engine = create_engine(f"sqlite:///{p}")
    try:
        db.init()
        assert "context" in {c["name"] for c in inspect(db.engine).get_columns("application")}
        with db.Session(db.engine) as s:
            r = s.get(db.Application, "OLD1")
            assert r.context == {} and r.evidence == [] and r.status == "open"
    finally:
        db.engine = old
