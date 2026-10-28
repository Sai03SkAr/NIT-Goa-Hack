"""Biometric agent (D4): selfie<->card<->registry match, face reuse, liveness (client + server re-check),
virtual camera, passive replay hints. Voice / fingerprint are SIMULATED and never enter the fraud model."""
import hashlib
import time

import numpy as np

from app.modules.biometric import face as F
from app.schemas import ModuleResult, reason

VIRTUAL_TOKENS = ("virtual", "obs", "manycam", "xsplit", "snap camera", "droidcam", "vcam", "splitcam")


def extract(selfie_bgr: np.ndarray, card_norm_bgr: np.ndarray) -> dict:
    s = F.embed(selfie_bgr)
    c = F.embed(F.card_portrait(card_norm_bgr))
    return {"selfie": s, "card": c, "passive": F.passive(selfie_bgr)}


def verify_frames(frames_bgr: list[np.ndarray]) -> dict:
    """Server re-check of liveness: frames must be ONE identity with DIFFERENT head poses."""
    es = [F.embed(f) for f in frames_bgr]
    es = [e for e in es if e]
    if len(es) < 2:
        return {"consistent": False, "why": "faces_missing"}
    sims = [F.sim(es[i]["emb"], es[j]["emb"]) for i in range(len(es)) for j in range(i + 1, len(es))]
    yaws = [e["pose"][1] for e in es if e["pose"]]
    spread = (max(yaws) - min(yaws)) if yaws else 0.0
    ok = min(sims) > F.threshold() and spread > 8
    return {"consistent": bool(ok), "min_sim": round(min(sims), 3), "yaw_spread": round(spread, 1)}


def virtual_camera(labels: list[str]) -> bool:
    return any(t in (l or "").lower() for l in labels for t in VIRTUAL_TOKENS)


def simulated_voice(app_id: str, reg_sim: float) -> float:
    """SIMULATED speaker check: correlated with the registry face result + deterministic noise.
    Not class-conditional on the label, so it can't leak ground truth into the demo."""
    noise = int(hashlib.md5(app_id.encode()).hexdigest()[:6], 16) / 0xFFFFFF - 0.5
    base = 0.85 if (not np.isnan(reg_sim) and reg_sim > F.threshold()) else 0.3
    return float(np.clip(base + 0.25 * noise, 0, 1))


def assess(ext: dict, registry_emb, liveness: dict, camera_labels: list[str], reuse: dict,
           registry_face_url: str | None = None, active_camera: str | None = None) -> ModuleResult:
    t0 = time.time()
    R, f = [], {}
    thr = F.threshold()
    se = ext["selfie"]["emb"] if ext["selfie"] else None
    ce = ext["card"]["emb"] if ext["card"] else None
    f["bio_selfie_found"] = float(se is not None)
    f["bio_card_found"] = float(ce is not None)
    f["bio_sim_card"] = F.sim(se, ce)
    f["bio_sim_registry"] = F.sim(se, registry_emb)
    f["bio_sim_card_registry"] = F.sim(ce, registry_emb)
    if se is None or ce is None:
        R.append(reason("BIO_NO_FACE", 0.3))
    if f["bio_sim_card"] < thr:
        R.append(reason("BIO_CARD_FACE_MISMATCH", 0.35))
    if f["bio_sim_registry"] < thr:
        R.append(reason("BIO_REGISTRY_FACE_MISMATCH", 0.45))

    f["bio_face_reuse_diff_name"] = float(reuse.get("diff_name", 0))
    f["bio_face_reuse_max_sim"] = float(reuse.get("max_sim", 0))
    if reuse.get("diff_name", 0) > 0:
        R.append(reason("BIO_FACE_REUSED", 0.5))

    # judge the camera actually streaming; an installed-but-unused OBS is not an injection
    vc = bool(liveness.get("virtual_camera")) or virtual_camera([active_camera] if active_camera else camera_labels)
    f["bio_virtual_cam"] = float(vc)
    # A partner on minimum KYC may never run a live check. That is missing evidence (NaN to the model, REVIEW floor
    # in hard_rules), not a failed challenge, so it must not be scored or labelled as an injection attempt.
    performed = liveness.get("performed", True) is not False
    f["bio_liveness_performed"] = float(performed)
    f["bio_liveness_pass"] = float(bool(liveness.get("passed"))) if performed else float("nan")
    f["bio_frames_consistent"] = float(bool(liveness.get("frames_consistent", True))) if performed else float("nan")
    if vc:
        R.append(reason("BIO_VIRTUAL_CAMERA", 0.6))
    if not performed:
        R.append(reason("BIO_LIVENESS_NOT_PERFORMED", 0.25))
    elif not liveness.get("passed"):
        R.append(reason("BIO_LIVENESS_FAIL", 0.5))
    if performed and not liveness.get("frames_consistent", True):
        R.append(reason("BIO_FRAMES_INCONSISTENT", 0.4))

    p = ext["passive"]
    f["bio_blur"], f["bio_moire"] = p["blur"], p["moire"]
    if p["moire"] > 160:  # genuine-selfie p99 on the train split; blur didn't separate replay from genuine
        R.append(reason("BIO_SCREEN_REPLAY", 0.2))

    hard = 1.0 if (vc or (performed and not liveness.get("passed"))) else 0.0
    s = 0.0
    for v, w in ((f["bio_sim_card"], .3), (f["bio_sim_registry"], .45)):
        s += w * (1.0 if np.isnan(v) else float(np.clip((thr + 0.15 - v) / 0.3, 0, 1)))
    s += 0.25 * min(1, f["bio_face_reuse_diff_name"])
    risk = max(hard * 0.9, min(1, s))
    f["bio_risk"] = risk
    return ModuleResult(module="biometric", risk=round(risk, 3), reasons=R, features=f,
                        latency_ms=int((time.time() - t0) * 1000),
                        evidence={"threshold": thr, "sim_card": f["bio_sim_card"], "sim_registry": f["bio_sim_registry"],
                                  "liveness": liveness, "passive": p, "reuse": reuse,
                                  "registry_face_url": registry_face_url})
