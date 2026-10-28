"""Decision policy: approval needs every required check to PASS; missing or simulated evidence never counts."""
import math

from app import policy as P

OK = {"prob": 0.01, "status": "ok"}


def all_pass(**over):
    f = {f"ev_{c}": P.CODE[P.PASS] for c in P.REQUIRED}
    f.update(bio_blur=100.0, doc_ocr_conf=0.95, bio_media_reuse=0.0, cor_device_people_7d=0.0)
    f.update(over)
    return f


def test_all_pass_low_risk_approves():
    d = P.decide(all_pass(), OK)
    assert d["band"] == "APPROVE" and d["approval_eligible"] and not d["unresolved"]


def test_missing_check_is_not_provided_and_blocks_approval():
    f = all_pass()
    del f["ev_liveness"]
    d = P.decide(f, OK)
    assert d["band"] == "REVIEW" and d["checks"]["liveness"] == P.NOT_PROVIDED
    assert "EV_LIVENESS_NOT_PROVIDED" in d["rule_codes"]


def test_nan_check_is_not_success():
    assert P.status({"ev_face_card": math.nan}, "face_card") == P.NOT_PROVIDED


def test_model_unavailable_never_approves_and_has_no_probability():
    d = P.decide(all_pass(), {"prob": None, "status": "unavailable"})
    assert d["band"] == "REVIEW" and d["prob"] is None and "MODEL_UNAVAILABLE" in d["rule_codes"]


def test_stale_model_treated_as_unavailable():
    assert P.decide(all_pass(), {"prob": 0.01, "status": "stale"})["band"] == "REVIEW"


def test_signature_fail_is_hard_reject_even_at_low_score():
    d = P.decide(all_pass(ev_doc_signature=P.CODE[P.FAIL]), OK)
    assert d["band"] == "REJECT" and d["forced"] == "REJECT" and "DOC_QR_SIG_INVALID" in d["rule_codes"]


def test_unreadable_print_is_review_not_reject():
    d = P.decide(all_pass(ev_doc_consistency=P.CODE[P.UNAVAILABLE]), OK)
    assert d["band"] == "REVIEW"


def test_poor_photos_cap_model_reject_to_review():
    d = P.decide(all_pass(bio_blur=5.0), {"prob": 0.99, "status": "ok"})
    assert d["band"] == "REVIEW" and d["checks"]["capture_quality"] == P.FAIL


def test_model_can_reject_when_evidence_is_clear():
    assert P.decide(all_pass(), {"prob": 0.99, "status": "ok"})["band"] == "REJECT"


def test_media_reuse_and_genai_marker_block_approval():
    assert P.decide(all_pass(bio_media_reuse=1.0), OK)["band"] == "REVIEW"
    assert P.decide(all_pass(meta_genai_selfie=1.0), OK)["band"] == "REVIEW"


def test_mule_herding_holds_for_review_never_rejects_by_itself():
    d = P.decide(all_pass(cor_device_people_7d=2.0), OK)
    assert d["band"] == "REVIEW" and d["checks"]["device_network"] == P.FAIL


def test_policy_never_edits_the_probability():
    assert P.decide(all_pass(ev_liveness=P.CODE[P.FAIL]), {"prob": 0.123, "status": "ok"})["prob"] == 0.123


def test_simulated_voice_is_informational_only():
    ev = {e["check"]: e for e in P.evidence_list(all_pass())}
    assert ev["voice"]["status"] == P.SIMULATED and not ev["voice"]["required"]
    assert "voice" not in P.REQUIRED
