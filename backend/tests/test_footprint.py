"""Consented digital footprint: only contradictions count, a missing or thin footprint is neutral, and it never decides."""
from datetime import date

import numpy as np
import pytest

from app import db, learning, policy
from app.graph.pipeline import footprint_module
from app.modules.footprint import agent, provider

TODAY = date(2026, 10, 1)
FORM = {"name": "Riya Kamat", "dob": "04/09/1999", "email": "riya@example.com", "phone": "9822001122"}


def _unit(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


ME, OTHER = _unit(1), _unit(2)


@pytest.fixture
def source(monkeypatch):
    data = {"email": {}, "phone": {}, "linked": {}, "photos": {"me": ME, "other": OTHER}, "consent": {}}
    monkeypatch.setattr(provider, "_sim", lambda: data)
    return data


def test_no_consent_means_no_lookup_and_no_effect(source):
    r = agent.assess(FORM, False, ME, TODAY)
    assert r.features["ev_footprint"] == policy.CODE[policy.NOT_PROVIDED]
    assert r.reasons == [] and r.evidence["status"] == "not consented"


def test_no_footprint_or_a_new_email_never_counts_against_anyone(source):
    none = agent.assess(FORM, True, ME, TODAY)  # consented, but nothing is known about this person
    assert none.features["ev_footprint"] == policy.CODE[policy.NOT_PROVIDED] and none.reasons == []
    source["email"]["riya@example.com"] = {"first_seen": "2026-09-28", "services": 0}  # made this week to apply
    thin = agent.assess(FORM, True, ME, TODAY)
    assert thin.features["ev_footprint"] == policy.CODE[policy.PASS] and thin.reasons == []
    assert thin.evidence["depth"] == "thin" and thin.evidence["notes"] and thin.evidence["score"] == 100


def test_linked_account_in_another_name_is_a_contradiction(source):
    source["linked"]["riya@example.com"] = {"provider": "google", "name": "Suresh Pai", "created": "2020-01-01", "photo": None}
    r = agent.assess(FORM, True, ME, TODAY)
    assert r.features["ev_footprint"] == policy.CODE[policy.FAIL]
    assert [x.code for x in r.reasons] == ["FP_LINKED_NAME_MISMATCH"]


def test_first_name_only_profile_is_partial_not_a_contradiction(source):
    source["linked"]["9822001122"] = {"provider": "linkedin", "name": "Riya", "created": "2019-05-01", "photo": None}
    r = agent.assess(FORM, True, ME, TODAY)
    assert r.reasons == [] and r.evidence["checks"][0]["result"] == "partial"


def test_profile_picture_is_compared_with_the_selfie(source):
    source["linked"]["riya@example.com"] = {"provider": "google", "name": "Riya Kamat", "created": "2018-01-01", "photo": "me"}
    same = agent.assess(FORM, True, ME, TODAY)
    assert same.features["ev_footprint"] == policy.CODE[policy.PASS] and same.evidence["score"] == 100
    source["linked"]["riya@example.com"]["photo"] = "other"
    diff = agent.assess(FORM, True, ME, TODAY)
    assert [x.code for x in diff.reasons] == ["FP_LINKED_PHOTO_MISMATCH"] and diff.evidence["score"] == 50


def test_an_email_older_than_its_owner_is_a_contradiction(source):
    source["email"]["riya@example.com"] = {"first_seen": "2004-01-01", "services": 9}  # owner was 4
    r = agent.assess(FORM, True, None, TODAY)
    assert [x.code for x in r.reasons] == ["FP_EMAIL_PREDATES_APPLICANT"]


def test_unconfigured_provider_is_unavailable_not_invented(monkeypatch):
    monkeypatch.setattr(provider, "FOOTPRINT_PROVIDER", "licensed-vendor")
    r = agent.assess(FORM, True, ME, TODAY)
    assert r.features["ev_footprint"] == policy.CODE[policy.UNAVAILABLE]


def test_pipeline_reads_the_separate_consent(source):
    source["linked"]["riya@example.com"] = {"provider": "google", "name": "Suresh Pai", "created": "2020-01-01", "photo": None}
    app = {"form": FORM, "ts": "2026-10-01T10:00:00", "consent": {"accepted": True}}
    assert footprint_module(app, ME)["evidence"]["status"] == "not consented"
    app["consent"]["footprint"] = True
    assert footprint_module(app, ME)["features"]["ev_footprint"] == policy.CODE[policy.FAIL]


def test_footprint_is_informational_and_never_coached():
    assert "footprint" in policy.INFORMATIONAL and "footprint" not in policy.REQUIRED
    f = {f"ev_{c}": policy.CODE[policy.PASS] for c in policy.REQUIRED}
    f.update(bio_blur=100.0, doc_ocr_conf=0.95, bio_media_reuse=0.0, cor_device_people_7d=0.0,
             ev_footprint=policy.CODE[policy.FAIL])
    assert policy.decide(f, {"prob": 0.01, "status": "ok"})["band"] == "APPROVE"
    r = db.Application(app_id="F1", ts="2026-10-01T00:00:00", band="APPROVE", status="open", evidence=policy.evidence_list(f))
    t = learning.tips_for(r)
    assert t["manual_review"] is False and "footprint" not in str(t).lower()  # other fixable tips (location) may appear
