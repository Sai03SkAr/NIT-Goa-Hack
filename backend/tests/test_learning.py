"""The learning loop proposes from outcomes, never applies on its own, and never coaches fraud signals."""
import numpy as np
import pytest

from app import db, learning
import learning_data as LD  # tests/ is on sys.path (no package: an installed "tests" package would shadow it)

AUTH = {"X-Analyst-Key": "test-analyst-key"}


class RT:
    bands = {"approve_below": 0.3, "reject_at": 0.7}


@pytest.fixture()
def history(client):
    LD.wipe()
    LD.load(LD.make_rows())
    yield
    LD.wipe()


def test_psi_is_zero_for_the_same_distribution_and_large_for_a_shift():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 2000)
    assert learning.psi(a, rng.normal(0, 1, 2000)) < 0.05
    assert learning.psi(a, rng.normal(1.5, 1, 2000)) > learning.PSI_DRIFT


def test_the_systems_own_decision_is_never_a_label():
    r = db.Application(app_id="X1", ts="2026-10-01T00:00:00", band="REJECT", status="open", source="live")
    assert learning.label_of(r) == (None, "")
    r.status = "approved"
    assert learning.label_of(r) == (0, "analyst")


def test_cycle_proposes_better_bands_and_nothing_changes_until_approved(history):
    c = learning.run_cycle("manual", RT.bands)
    props = {p["key"]: p for p in learning.proposals("proposed")}
    assert c["proposals"] == len(props)
    b = props["bands"]
    assert b["change"]["bands"]["approve_below"] >= 0.45      # genuine people score up to 0.5 in this history
    assert b["impact"]["after"]["cost"] < b["impact"]["before"]["cost"]
    assert b["applicable"] and all(g["ok"] for g in b["safeguards"])
    assert RT.bands["approve_below"] == 0.3                       # proposing changed nothing

    rt = RT()
    rt.bands = dict(RT.bands)
    out = learning.decide(b["id"], "apply", "analyst:a1", rt)
    assert out["status"] == "applied" and rt.bands == b["change"]["bands"]
    assert out["previous"]["bands"] == RT.bands
    back = learning.decide(b["id"], "rollback", "analyst:a1", rt)
    assert back["status"] == "rolled_back" and rt.bands == RT.bands
    with db.session() as s:
        acts = [a.action for a in s.exec(db.select(db.AuditLog).where(db.AuditLog.app_id == "LEARNING")).all()]
    assert any(a.endswith(":applied") for a in acts) and any(a.endswith(":rolled_back") for a in acts)
    assert db.verify_audit()["ok"]


def test_monitoring_finds_drift_health_and_a_noisy_signal(history):
    d = learning.drift()
    beh = next(f for f in d["features"] if f["feature"] == "beh_iki_cv")
    assert beh["status"] == "drift"
    live = next(c for c in d["checks"] if c["check"] == "liveness")
    assert live["status"] == "unavailable"
    learning.run_cycle("manual", RT.bands)
    keys = {p["key"] for p in learning.proposals("proposed")}
    assert "unavailable:liveness" in keys
    assert "noisy:BEH_PASTE" in keys
    assert "coach:capture_quality" in keys


def test_a_new_cycle_supersedes_the_open_proposal_with_the_same_key(history):
    learning.run_cycle("manual", RT.bands)
    first = next(p for p in learning.proposals("proposed") if p["key"] == "bands")
    learning.run_cycle("manual", RT.bands)
    statuses = {p["id"]: p["status"] for p in learning.proposals()}
    assert statuses[first["id"]] == "superseded"
    assert sum(1 for p in learning.proposals("proposed") if p["key"] == "bands") == 1


def test_advisories_cannot_be_applied(history):
    learning.run_cycle("manual", RT.bands)
    adv = next(p for p in learning.proposals("proposed") if p["kind"] == "advisory")
    with pytest.raises(ValueError):
        learning.decide(adv["id"], "apply", "analyst:a1", RT())
    assert learning.decide(adv["id"], "acknowledge", "analyst:a1", RT())["status"] == "acknowledged"


def test_too_few_labels_means_no_band_proposal(client):
    LD.wipe()
    LD.load(LD.make_rows(n=40, labelled=0.3, drift=False, unavailable=False))
    try:
        learning.run_cycle("manual", RT.bands)
        assert "bands" not in {p["key"] for p in learning.proposals("proposed")}
    finally:
        LD.wipe()


def test_one_analyst_writing_all_the_feedback_cannot_move_the_bands(client):
    LD.wipe()
    LD.load(LD.make_rows(), analysts=("analyst:mallory",))
    try:
        learning.run_cycle("manual", RT.bands)
        b = next(p for p in learning.proposals("proposed") if p["key"] == "bands")
        assert b["applicable"] is False
        assert not next(g for g in b["safeguards"] if "analyst" in g["rule"])["ok"]
    finally:
        LD.wipe()


def test_retraining_waits_for_a_base_model(history):
    r = learning.challenger_readiness(learning.feedback())
    assert r["ready"] is False and "model" in r["why"]


def test_tips_name_fixable_issues_and_never_fraud_signals():
    r = db.Application(app_id="X2", ts="2026-10-01T00:00:00", band="REVIEW", status="open",
                       evidence=LD.evidence({"capture_quality": "FAIL", "device_network": "FAIL", "liveness": "NOT_PROVIDED"}))
    t = learning.tips_for(r)
    checks = [x["check"] for x in t["tips"]]
    assert checks and set(checks) <= {"capture_quality", "liveness"}
    assert t["manual_review"] is True
    text = str(t).lower()
    assert "device" not in text and "ring" not in text and "other bank" not in text


def test_a_rejected_applicant_is_not_coached():
    r = db.Application(app_id="X4", ts="2026-10-01T00:00:00", band="REJECT", status="open", evidence=LD.evidence({"capture_quality": "FAIL"}))
    t = learning.tips_for(r)
    assert t["tips"] == [] and t["manual_review"] is False


def test_an_approved_applicant_gets_no_tips():
    r = db.Application(app_id="X3", ts="2026-10-01T00:00:00", band="APPROVE", status="open", evidence=LD.evidence())
    t = learning.tips_for(r)
    assert t["tips"] == [] and t["manual_review"] is False


def test_learning_api_is_analyst_only_and_works(client, history):
    assert client.get("/api/learning/overview").status_code == 401
    assert client.post("/api/learning/cycle").status_code == 401
    c = client.post("/api/learning/cycle", headers=AUTH)
    assert c.status_code == 200 and c.json()["proposals"] > 0
    ov = client.get("/api/learning/overview", headers=AUTH).json()
    assert ov["proposals"]["open"] > 0 and ov["feedback"]["analyst"] > 100
    for path in ("drift", "feedback", "proposals", "cycles", "coaching", "tips/LX0001"):
        assert client.get(f"/api/learning/{path}", headers=AUTH).status_code == 200, path
    adv = next(p for p in client.get("/api/learning/proposals?status=proposed", headers=AUTH).json() if p["kind"] == "advisory")
    assert client.post(f"/api/learning/proposals/{adv['id']}", json={"action": "apply"}, headers=AUTH).status_code == 409
    assert client.post("/api/learning/proposals/P-NOPE", json={"action": "dismiss"}, headers=AUTH).status_code == 404


def test_the_applicants_own_result_carries_tips_and_no_fraud_signal(client):
    from fastapi.testclient import TestClient
    from app import main, security as S
    from app.main import app
    LD.wipe()
    r = db.Application(app_id="LTIP1", ts="2026-10-28T10:00:00", band="REVIEW", status="open", source="live",
                       evidence=LD.evidence({"capture_quality": "FAIL", "device_network": "FAIL"}))
    LD.load([r])
    try:
        me = TestClient(app)
        me.post("/api/session")
        job = main.Job("LTIP1", S.read_token(me.cookies.get(S.APPLICANT_COOKIE), "applicant"))
        job.done = True
        main.JOBS["LTIP1"] = job
        out = me.get("/api/apply/LTIP1/result").json()
        assert [t["check"] for t in out["coaching"]["tips"]] == ["capture_quality"]
        assert out["coaching"]["manual_review"] is True
        assert "device" not in str(out["coaching"]).lower()
    finally:
        main.JOBS.pop("LTIP1", None)
        LD.wipe()
