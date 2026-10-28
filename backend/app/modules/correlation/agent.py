"""Correlation agent (D1): specificity-weighted identity graph, rings, family exception."""
import time

import numpy as np

from app.schemas import ModuleResult, reason


def assess(rec: dict, hist, commit: bool = True) -> ModuleResult:
    """Links the record into history (commit=True adds it) and scores its connected component."""
    t0 = time.time()
    edges = hist.link(rec)
    R, f = [], {}
    kinds_total: dict[str, int] = {}
    for kinds in edges.values():
        for k in kinds:
            kinds_total[k] = kinds_total.get(k, 0) + 1
    f["cor_weighted_degree"] = sum(hist.edge_weight(k) for k in edges.values())
    f["cor_strong_links"] = float(sum(1 for k in edges.values() if hist.edge_weight(k) >= 0.45))
    a = rec["attrs"]
    f["cor_device_names"] = float(hist.shared_names("device", a["device"], rec["name"]))
    f["cor_phone_names"] = float(hist.shared_names("phone", a["phone"], rec["name"]))
    f["cor_address_names"] = float(hist.shared_names("address", a["address"], rec["name"]))
    f["cor_id_names"] = float(hist.shared_names("id_hash", a["id_hash"], rec["name"]))
    f["cor_ip_names"] = float(hist.shared_names("ip", a["ip"], rec["name"]))
    # computed before this record is added, so it counts OTHER people only
    f["cor_device_people_7d"] = float(hist.device_people(a["device"], rec["ts"], rec["name"])) if a["device"] else np.nan

    if commit:
        i = hist.add(rec, edges)
        comp = hist.component(i)
    else:
        comp = {"size": 1 + len(edges), "surname_share": 1.0, "span_days": 0, "face_edges": kinds_total.get("face", 0),
                "ks_edges": kinds_total.get("keystroke", 0), "device_edges": 0, "email_edges": 0, "members": []}
    f["cor_comp_size"] = float(comp["size"])
    f["cor_comp_surname_share"] = comp["surname_share"]
    f["cor_comp_span_days"] = comp["span_days"]
    f["cor_comp_face_edges"] = float(comp["face_edges"])
    f["cor_comp_ks_edges"] = float(comp["ks_edges"])
    f["cor_comp_email_edges"] = float(comp["email_edges"])

    family = (comp["size"] >= 2 and comp["surname_share"] >= 0.6 and comp["face_edges"] == 0
              and comp["ks_edges"] == 0 and comp["email_edges"] == 0)
    f["cor_family_pattern"] = float(family)
    ring = comp["size"] >= 3 and not family and (comp["face_edges"] + comp["ks_edges"] + comp["email_edges"] + comp["device_edges"]) >= 2
    ring_score = min(1.0, 0.15 * comp["size"] + 0.2 * comp["face_edges"] + 0.1 * comp["ks_edges"]
                     + 0.1 * comp["email_edges"]) if ring else 0.0
    f["cor_ring_score"] = ring_score
    if ring:
        R.append(reason("COR_RING_MEMBER", 0.5 * ring_score + 0.2))
    if f["cor_device_names"] > 0 and not family:
        R.append(reason("COR_SHARED_DEVICE", 0.2))
    if f["cor_phone_names"] > 0 and not family:
        R.append(reason("COR_SHARED_PHONE", 0.15))
    if f["cor_device_people_7d"] >= 2:
        R.append(reason("COR_MULE_HERDING", 0.3))
    if f["cor_id_names"] > 0:
        R.append(reason("COR_SHARED_ID", 0.45))
    if family:
        R.append(reason("COR_FAMILY_PATTERN", -0.15))

    risk = max(0.0, min(1.0, sum(r.weight for r in R)))
    f["cor_risk"] = risk
    return ModuleResult(module="correlation", risk=round(risk, 3), reasons=R, features=f,
                        latency_ms=int((time.time() - t0) * 1000),
                        evidence={"component": comp, "links": {hist.apps[j]["app_id"]: {k: round(v, 3) for k, v in kd.items()}
                                                               for j, kd in list(edges.items())[:25]}})
