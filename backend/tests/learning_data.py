"""Synthetic outcome history for the learning loop: the right answers are known by construction.

Genuine applicants score 0.0-0.5 and fraud 0.55-1.0, so the cost-optimal approve cut-off is about 0.5, not the
shipped 0.3. Behaviour shifts in the last week (drift), one capture check stops running (health), and a paste
signal fires on genuine people that analysts approve (a noisy signal).
"""
from datetime import datetime, timedelta

import numpy as np

from app import db, policy

END = datetime(2026, 10, 28, 18, 0)


def evidence(fail: dict | None = None):
    fail = fail or {}
    return [{"check": c, "label": lab, "source": src, "required": True, "status": fail.get(c, "PASS")}
            for c, (lab, src) in policy.REQUIRED.items()]


def make_rows(n=300, seed=1, prefix="LX", drift=True, unavailable=True, labelled=0.6):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        fraud = rng.random() < 0.3
        recent = i >= int(n * 0.8)
        prob = float(rng.uniform(0.55, 1.0) if fraud else rng.uniform(0.0, 0.5))
        band = "REJECT" if prob >= 0.7 else "REVIEW" if prob >= 0.3 else "APPROVE"
        fail = {}
        if not fraud and rng.random() < 0.15:
            fail["capture_quality"] = "FAIL"
        if unavailable and recent and rng.random() < 0.5:
            fail["liveness"] = "UNAVAILABLE"
        iki = rng.normal(0.9 if (drift and recent) else 0.5, 0.08)
        reasons = []
        if not fraud and rng.random() < 0.25:
            reasons.append({"code": "BEH_PASTE", "text": "Details were pasted into the form", "weight": 0.2})
        if fraud:
            reasons.append({"code": "COR_RING_MEMBER", "text": "Part of a densely linked cluster of identities", "weight": 0.5})
        status = "open"
        if rng.random() < labelled:
            status = "rejected" if fraud else "approved"
        rows.append(db.Application(
            app_id=f"{prefix}{i:04d}", ts=(END - timedelta(hours=(n - i) * 2)).isoformat(timespec="seconds"),
            source="live", name=f"Person {i}", id_last4=f"{i:04d}", prob=prob, band=band, status=status,
            fraud_type="ring" if fraud else "none", evidence=evidence(fail),
            modules=[{"module": "behavior", "risk": 0.2, "reasons": reasons, "features": {"beh_iki_cv": float(iki), "beh_fill_s": float(rng.normal(40, 5))}},
                     {"module": "correlation", "risk": 0.5 if fraud else 0.1, "reasons": [], "features": {"cor_comp_size": float(rng.integers(1, 4))}}]))
    return rows


def load(rows, analysts=("analyst:a1", "analyst:a2", "analyst:a3")):
    """Store the rows, and an audit entry for each disposition, written by the given analysts in turn."""
    with db.session() as s:
        for r in rows:
            s.merge(r)
        s.commit()
    with db.session() as s:
        last = s.exec(db.select(db.AuditLog).order_by(db.AuditLog.id.desc()).limit(1)).first()
        prev = last.hash if last else ""
        for i, r in enumerate(x for x in rows if x.status in ("approved", "rejected")):
            e = db.AuditLog(app_id=r.app_id, action=f"override:open->{r.status}", note="checked", actor=analysts[i % len(analysts)], prev_hash=prev)
            e.hash = db._entry_hash(prev, e)
            prev = e.hash
            s.add(e)
        s.commit()


def wipe():
    from app import learning
    with db.session() as s:
        for t in (db.Application, learning.Proposal, learning.Cycle, db.AuditLog):
            for r in s.exec(db.select(t)).all():
                s.delete(r)
        s.commit()
