"""Genuine-applicant profile (IDRBT-style explainable one-class rules, one-shot federation) and decision counterfactuals."""
import numpy as np

from app import policy
from app.fusion import profile

FEATS = ["a", "b", "c"]


def _genuine(n=300, seed=0):
    r = np.random.default_rng(seed)
    return np.column_stack([r.normal(0, 1, n), r.normal(5, 1, n), r.integers(0, 2, n)]).astype(float)


def test_profile_flags_unlike_genuine_and_names_the_broken_rule():
    G = _genuine()
    P = profile.calibrate(profile.fit(G, FEATS, k=3), _genuine(200, seed=1))
    inside = profile.explain(P, {"a": 0.1, "b": 5.0, "c": 1.0})
    outside = profile.explain(P, {"a": 0.1, "b": 40.0, "c": 1.0})
    assert not inside["outside"] and inside["rules"] == []
    assert outside["outside"] and outside["rules"][0]["feature"] == "b"
    rule = outside["rules"][0]  # the broken rule shows the genuine range, which excludes the outlier value
    assert rule["value"] == 40.0 and rule["low"] < rule["high"] < 40.0


def test_profile_needs_no_fraud_labels_and_tolerates_missing_values():
    P = profile.calibrate(profile.fit(_genuine(), FEATS, k=3), _genuine(200, seed=1))
    r = profile.explain(P, {"a": float("nan"), "b": 5.0})  # missing -> genuine median, never "outside" by itself
    assert not r["outside"]


def test_calibration_holds_about_two_percent_of_genuine():
    P = profile.calibrate(profile.fit(_genuine(), FEATS, k=3), _genuine(400, seed=2))
    s, _, _ = profile.score(P, _genuine(400, seed=3))
    assert (s > P["threshold"]).mean() < 0.08


def test_federation_shares_summaries_not_rows_and_still_works():
    G = _genuine(600)
    med = np.median(G, axis=0)
    scale = profile._robust(G, med)
    shards = [G[:200], G[200:400], G[400:]]
    summaries = [s for x in shards for s in profile.summarise(x, med, scale, k_local=3)]
    assert all(set(s) == {"centre", "n", "lo", "hi"} for s in summaries)  # no customer rows leave a bank
    assert sum(s["n"] for s in summaries) <= 600
    P = profile.calibrate(profile.federate(summaries, FEATS, med, scale, k_global=3), _genuine(200, seed=1))
    assert P["source"] == "federated"
    assert profile.explain(P, {"a": 0.0, "b": 60.0, "c": 0.0})["outside"]
    assert not profile.explain(P, {"a": 0.0, "b": 5.0, "c": 0.0})["outside"]


def test_profile_is_informational_never_a_decision_rule():
    assert "profile" in policy.INFORMATIONAL and "profile" not in policy.REQUIRED
    f = {f"ev_{c}": policy.CODE[policy.PASS] for c in policy.REQUIRED}
    f.update(bio_blur=100.0, doc_ocr_conf=0.95, bio_media_reuse=0.0, cor_device_people_7d=0.0,
             ev_profile=policy.CODE[policy.FAIL])
    assert policy.decide(f, {"prob": 0.01, "status": "ok"})["band"] == "APPROVE"


def test_counterfactual_controllable_set_excludes_what_an_applicant_cannot_change():
    from app.fusion.counterfactual import controllable
    names = ["beh_fill_time", "cor_comp_size", "cor_comp_face_edges", "cor_id_names", "bio_sim_registry", "doc_sig_invalid"]
    assert controllable(names) == ["beh_fill_time", "cor_comp_size"]


def test_counterfactual_is_analyst_only(client):
    assert client.get("/api/apps/X/counterfactual").status_code == 401
    assert client.get("/api/apps/X/counterfactual", headers={"X-Partner-Key": "kh_test_3e8d14b9c702"}).status_code == 401
