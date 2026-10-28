"""Liveness challenges, signed QR, audit chain, telemetry, provenance markers."""
import time

import numpy as np


def test_challenge_is_single_use_and_session_bound():
    from app import liveness_sessions as L
    c = L.issue("s1")
    assert sorted(c["sequence"]) == ["turn_left", "turn_right"]
    assert L.consume(c["challenge_id"], "s2")[1] == L.WRONG_SESSION
    c = L.issue("s1")
    assert L.consume(c["challenge_id"], "s1")[1] == L.VALID
    assert L.consume(c["challenge_id"], "s1")[1] == L.REUSED
    assert L.consume("made-up", "s1")[1] == L.UNKNOWN


def test_challenge_expiry(monkeypatch):
    from app import liveness_sessions as L
    c = L.issue("s1")
    real = time.time
    monkeypatch.setattr(L.time, "time", lambda: real() + 10_000)
    assert L.consume(c["challenge_id"], "s1")[1] == L.EXPIRED


def test_wrong_frame_count_fails_without_face_model():
    from app import policy as P
    from app.modules.biometric import agent as bio
    r = bio.verify_challenge([np.zeros((10, 10, 3), np.uint8)], ["turn_left", "turn_right"], None)
    assert r["status"] == P.FAIL and "BIO_CHALLENGE_FRAMES" in r["codes"]


def test_upload_path_is_not_provided_and_expired_is_unavailable():
    from app import policy as P
    from app.modules.biometric import agent as bio
    assert bio.not_provided()["status"] == P.NOT_PROVIDED
    assert bio.challenge_rejected("EXPIRED")["status"] == P.UNAVAILABLE
    assert bio.challenge_rejected("REUSED")["status"] == P.FAIL


def test_qr_roundtrip_forgery_and_tamper():
    from app.modules.document import qr_sign as Q
    fields = {"n": "ASHA NAIK", "d": "01/01/1990", "g": "F", "id": "234567890123", "i": "05/06/2012"}
    text = Q.make_qr_text(fields)
    payload, st = Q.parse_and_verify(text)
    assert st == Q.VALID and payload["id"] == "234567890123"
    assert Q.parse_and_verify(Q.make_qr_text(fields, Q.forger_key()))[1] == Q.INVALID_SIG
    assert Q.parse_and_verify(Q.make_qr_text(fields, Q.forger_key(), kid="evil"))[1] == Q.UNTRUSTED_KEY
    assert Q.parse_and_verify("TID2|bm9wZQ|AAAA")[1] == Q.MALFORMED
    assert Q.parse_and_verify(None)[1] == Q.NOT_FOUND


def test_audit_chain_detects_tampering():
    from app import db
    db.init()
    db.audit(None, "A1", "decision:REVIEW", "x")
    db.audit(None, "A1", "override:open->approved", "checked by phone call")
    assert db.verify_audit()["ok"]
    with db.Session(db.engine) as s:
        e = s.exec(db.select(db.AuditLog).order_by(db.AuditLog.id.desc())).first()
        e.note = "edited later"
        s.add(e); s.commit()
    assert not db.verify_audit()["ok"]


def test_missing_telemetry_is_unknown_not_normal():
    from datetime import datetime
    from app.modules.behavior import agent as beh
    from app.modules.correlation.history import History
    app = {"app_id": "T1", "ts": datetime.now().isoformat(), "form": {"name": "Asha Naik", "id_number": "1", "email": "a@b.co"},
           "device": {}, "telemetry": {}}
    r = beh.assess(app, History.record(app, None), History(0.3))
    assert np.isnan(r.features["beh_fill_time"]) and not r.reasons


def test_genai_marker_and_media_hash():
    import cv2
    from app.modules.document.forensics import dhash, genai_marker
    assert genai_marker(b"\xff\xd8...Iptc4xmpExt:DigitalSourceType=trainedAlgorithmicMedia...") is not None
    assert genai_marker(b"\xff\xd8 plain camera jpeg c2pa manifest") is None  # C2PA alone is not a marker
    img = (np.random.default_rng(0).random((120, 100, 3)) * 255).astype(np.uint8)
    again = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])[1], cv2.IMREAD_COLOR)
    assert bin(dhash(img) ^ dhash(again)).count("1") <= 6


def test_mule_herding_counts_other_people_on_one_device():
    from datetime import datetime, timedelta
    from app.modules.correlation.history import History
    h = History(0.3)
    t = datetime(2026, 10, 1)
    for i, name in enumerate(["Asha Naik", "Rohan Desai", "Priya Kamat"]):
        h.add(History.record({"app_id": f"M{i}", "ts": t + timedelta(hours=i), "form": {"name": name, "id_number": str(i)},
                              "device": {"device_id": "D1"}, "telemetry": {}}, None))
    assert h.device_people("d1", t + timedelta(hours=5), "Meera Pai") == 3
    assert h.device_people("d1", t + timedelta(hours=5), "Kavya Naik") == 2  # same surname: household, not counted
    assert h.device_people("d1", t + timedelta(days=9), "Meera Pai") == 0
