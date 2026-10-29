"""Real Aadhaar Secure QR (UIDAI offline verification): parsing, signature, mobile hash, photo, and the registry path.
UIDAI's private key is of course not available, so QRs here are built in UIDAI's exact layout and signed by a test
certificate placed where the UIDAI certificate goes."""
import datetime as dt
import io
import shutil
from datetime import date

import cv2
import numpy as np
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image

from app.modules.document import aadhaar, qr_sign

FIELDS = {"reference_id": "3672" + "20240115103045123", "name": "Asha Verma", "dob": "14-08-1996", "gender": "F",
          "care_of": "D/O Ramesh Verma", "district": "North Goa", "landmark": "", "house": "12", "location": "Panaji",
          "pincode": "403001", "post_office": "Panaji", "state": "Goa", "street": "MG Road", "sub_district": "Tiswadi",
          "vtc": "Panaji"}


@pytest.fixture()
def uidai_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test stand-in for UIDAI")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    aadhaar.CERT_DIR.mkdir(parents=True, exist_ok=True)
    (aadhaar.CERT_DIR / "test.cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))
    yield key
    shutil.rmtree(aadhaar.CERT_DIR, ignore_errors=True)


def _jp2(color=(150, 110, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 48), color).save(buf, "JPEG2000")
    return buf.getvalue()


def test_secure_qr_verifies_and_maps_fields(uidai_key):
    text = aadhaar.make_secure_qr(FIELDS, _jp2(), uidai_key, mobile="9822001122", email="asha@example.com")
    assert aadhaar.looks_like(text)
    p, status, extras = aadhaar.parse_and_verify(text)
    assert status == qr_sign.VALID and p["issuer"].startswith("UIDAI")
    assert p["n"] == "ASHA VERMA" and p["d"] == "14/08/1996" and p["g"] == "F"
    assert p["id"] == "XXXXXXXX3672" and p["id_last4"] == "3672" and p["i"] == "15/01/2024"
    assert p["address"]["state"] == "Goa" and p["mobile_last4"] == "1122"
    assert aadhaar.photo_bgr(extras["photo"]).shape[:2] == (48, 40)
    # the mobile hash: SHA-256 chained n times, n = last Aadhaar digit (2 here)
    assert aadhaar.hash_matches("9822001122", extras["mobile_hash"], p["id_last4"][-1]) is True
    assert aadhaar.hash_matches("9999999999", extras["mobile_hash"], p["id_last4"][-1]) is False


def test_original_2019_layout_without_version_field(uidai_key):
    p, status, extras = aadhaar.parse_and_verify(aadhaar.make_secure_qr(FIELDS, _jp2(), uidai_key, version=""))
    assert status == qr_sign.VALID and p["format"] == "secure-qr-2019" and extras["mobile_hash"] is None


def test_any_change_breaks_the_signature(uidai_key):
    import zlib
    data = aadhaar.decompress(aadhaar.make_secure_qr(FIELDS, _jp2(), uidai_key))
    forged = data.replace(b"14-08-1996", b"14-08-1990")
    gz = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    text = str(int.from_bytes(gz.compress(forged) + gz.flush(), "big"))
    assert aadhaar.parse_and_verify(text)[1] == qr_sign.INVALID_SIG


def test_without_the_uidai_certificate_the_qr_is_read_but_never_valid(uidai_key):
    text = aadhaar.make_secure_qr(FIELDS, _jp2(), uidai_key)
    shutil.rmtree(aadhaar.CERT_DIR)
    p, status, _ = aadhaar.parse_and_verify(text)
    assert status == qr_sign.NO_KEYS and p["n"] == "ASHA VERMA"


def test_garbage_and_old_unsigned_xml():
    assert aadhaar.parse_and_verify("1" * 400)[1] == qr_sign.MALFORMED
    xml = ('<?xml version="1.0" encoding="UTF-8"?><PrintLetterBarcodeData uid="234567893672" name="Asha Verma" '
           'gender="F" yob="1996" pc="403001" state="Goa"/>')
    assert aadhaar.looks_like(xml)
    p, status, _ = aadhaar.parse_and_verify(xml)
    assert status == qr_sign.NO_KEYS and p["id"] == "XXXXXXXX3672" and p["format"] == "xml-unsigned"


def test_dense_secure_qr_is_read_from_an_image(uidai_key):
    import qrcode
    text = aadhaar.make_secure_qr(FIELDS, _jp2(), uidai_key, mobile="9822001122")
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=4)
    q.add_data(text)
    q.make(fit=True)
    img = cv2.cvtColor(np.array(q.make_image(fill_color="black", back_color="white").convert("RGB")), cv2.COLOR_RGB2BGR)
    canvas = cv2.copyMakeBorder(img, 60, 60, 300, 60, cv2.BORDER_CONSTANT, value=(245, 245, 245))  # QR on the card's side
    assert qr_sign.read_qr(canvas) == text


def test_document_agent_uses_the_signed_aadhaar_values(uidai_key):
    from app.modules.document import agent as doc
    text = aadhaar.make_secure_qr(FIELDS, _jp2(), uidai_key, mobile="9822001122")
    p, status, extras = aadhaar.parse_and_verify(text)
    lines = [{"text": "Government of India", "conf": 0.9}, {"text": "Asha Verma", "conf": 0.88},
             {"text": "DOB: 14/08/1996", "conf": 0.86}, {"text": "FEMALE", "conf": 0.8}, {"text": "2345 6789 3672", "conf": 0.9}]
    ext = {"qr_found": True, "qr_payload": p, "qr_status": status, "qr_kind": "aadhaar", "printed_lines": lines,
           "uidai_mobile_hash": extras["mobile_hash"], "ocr": {k: {"text": "", "conf": 0.0} for k in doc.SIGNED_FIELDS},
           "forensics": {"score": 0.1, "tex_ratio": 1.0, "font_dev": 0.1, "contrast_dev": 0.1}, "exif_editor": None,
           "provenance": {"ai": None}}
    form = {"name": "Asha Verma", "dob": "14/08/1996", "id_number": "234567893672", "pan": "", "phone": "9822001122"}
    r = doc.assess(ext, form, date(2026, 10, 29))
    f = r.features
    from app import policy as P
    assert f["ev_doc_signature"] == P.CODE[P.PASS] and f["ev_doc_consistency"] == P.CODE[P.PASS]
    assert f["ev_form_consistency"] == P.CODE[P.PASS] and f["doc_uidai_mobile_linked"] == 1.0
    assert r.evidence["qr_kind"] == "aadhaar" and "DOC_UIDAI_QR" in [x.code for x in r.reasons]
    # a different person's details typed into the form against this card
    r2 = doc.assess(ext, {**form, "name": "Rohit Kumar", "dob": "01/01/1990"}, date(2026, 10, 29))
    assert r2.features["ev_form_consistency"] == P.CODE[P.FAIL]
    # unreadable print on an unfamiliar layout: a person compares, never an automatic forgery verdict
    r3 = doc.assess({**ext, "printed_lines": [{"text": "Asha", "conf": 0.4}]}, form, date(2026, 10, 29))
    assert r3.features["ev_doc_consistency"] == P.CODE[P.UNAVAILABLE]


def test_registry_trusts_the_uidai_signature_for_people_outside_the_demo_registry(monkeypatch):
    from app import policy as P
    from app.modules.registry import agent as regm, mocks
    for f in ("uidai", "pan", "telecom", "ckyc", "bureau"):  # a real person: no demo registry knows them
        if hasattr(mocks, f):
            monkeypatch.setattr(mocks, f, lambda *a, **k: None)
    attested = {"n": "ASHA VERMA", "d": "14/08/1996"}
    form = {"name": "Asha Verma", "dob": "14/08/1996", "id_number": "234567893672", "pan": "ABCPV1234K", "phone": "9822001122"}
    r = regm.assess(form, date(2026, 10, 29), attested)
    assert r.features["ev_registry_identity"] == P.CODE[P.PASS]
    assert r.features["ev_pan_link"] == P.CODE[P.UNAVAILABLE]
    assert "REG_UIDAI_ATTESTED" in [x.code for x in r.reasons]
    wrong = regm.assess({**form, "dob": "01/01/1990"}, date(2026, 10, 29), attested)
    assert wrong.features["ev_registry_identity"] == P.CODE[P.FAIL]
    # without a verified Aadhaar, an unknown ID is still "not found"
    assert regm.assess(form, date(2026, 10, 29)).features["ev_registry_identity"] == P.CODE[P.FAIL]
