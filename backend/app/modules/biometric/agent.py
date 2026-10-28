"""Biometric agent (D4): selfie<->card<->registry match, face reuse, server-verified liveness challenge,
virtual camera hint, passive replay hints. Voice / fingerprint are SIMULATED and never enter the fraud model."""
import hashlib
import time

import cv2
import numpy as np

from app import policy as P
from app.modules.biometric import face as F
from app.schemas import ModuleResult, reason

VIRTUAL_TOKENS = ("virtual", "obs", "manycam", "xsplit", "snap camera", "droidcam", "vcam", "splitcam")


def extract(selfie_bgr: np.ndarray, card_norm_bgr: np.ndarray, selfie_raw: bytes | None = None) -> dict:
    from app.modules.document.forensics import genai_marker
    s = F.embed(selfie_bgr)
    c = F.embed(F.card_portrait(card_norm_bgr))
    return {"selfie": s, "card": c, "passive": F.passive(selfie_bgr), "genai_marker": genai_marker(selfie_raw)}


TURN_DELTA = 0.07  # nose-between-eyes shift vs the neutral frame; frontal jitter is ~0.02


def _tiny(img):
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (48, 48), interpolation=cv2.INTER_AREA).astype(np.float32)


def verify_challenge(frames_bgr: list[np.ndarray], sequence: list[str], selfie_emb) -> dict:
    """Server-side verification of a server-issued head-turn challenge.
    frames = [neutral, one frame per step in `sequence`], raw (unmirrored) camera frames.
    PASS needs: exactly one face per frame, every frame the same person as the selfie, distinct frames,
    and each step's head turn in the requested direction relative to the neutral frame."""
    codes, detail = [], {"sequence": sequence}
    if len(frames_bgr) != 1 + len(sequence):
        return {"status": P.FAIL, "codes": ["BIO_CHALLENGE_FRAMES"], "source": "server", "detail": detail}
    tiny = [_tiny(f) for f in frames_bgr]
    if min(float(np.abs(tiny[i] - tiny[j]).mean()) for i in range(len(tiny)) for j in range(i + 1, len(tiny))) < 1.0:
        codes.append("BIO_FRAMES_DUPLICATE")  # the same still submitted several times
    found = [F.faces(f) for f in frames_bgr]
    detail["faces_per_frame"] = [len(x) for x in found]
    if any(len(x) != 1 for x in found):
        codes.append("BIO_FRAME_FACE_COUNT")
        return {"status": P.FAIL, "codes": codes, "source": "server", "detail": detail, "consistent": None}
    fs = [x[0] for x in found]
    thr = F.threshold()
    anchor = selfie_emb if selfie_emb is not None else fs[0]["emb"]
    sims = [F.sim(anchor, f["emb"]) for f in fs]
    detail["sim_to_selfie"] = [round(x, 3) for x in sims]
    consistent = min(sims) >= thr
    if not consistent:
        codes.append("BIO_FRAMES_INCONSISTENT")
    base = fs[0]["nose_ratio"]
    deltas = [f["nose_ratio"] - base for f in fs[1:]]
    detail["turn_deltas"] = [round(d, 3) for d in deltas]
    turned = all((d >= TURN_DELTA) if step == "turn_left" else (d <= -TURN_DELTA) for step, d in zip(sequence, deltas))
    if not turned:
        codes.append("BIO_LIVENESS_FAIL")
    return {"status": P.PASS if not codes else P.FAIL, "codes": codes, "source": "server", "detail": detail,
            "consistent": consistent}


def not_provided(why: str = "no_challenge") -> dict:
    """Upload path / no camera: liveness was never shown to the server, so it cannot count as passed."""
    return {"status": P.NOT_PROVIDED, "codes": ["BIO_LIVENESS_NOT_PROVIDED"], "source": "none", "detail": {"why": why},
            "consistent": None}


def challenge_rejected(status: str) -> dict:
    """Challenge token problem. Expired is usually an innocent slow user (UNAVAILABLE); reuse/forgery is a FAIL."""
    st = P.UNAVAILABLE if status == "EXPIRED" else P.FAIL
    return {"status": st, "codes": ["BIO_CHALLENGE_INVALID"], "source": "server", "detail": {"challenge": status},
            "consistent": None}


def fixture_liveness(l: dict) -> dict:
    """Seeded population only: the generator labels each synthetic session's liveness outcome. These rows are never
    live camera evidence and the evaluation manifest says so."""
    ok = bool(l.get("passed")) and bool(l.get("frames_consistent", True))
    codes = [] if ok else (["BIO_LIVENESS_FAIL"] if not l.get("passed") else ["BIO_FRAMES_INCONSISTENT"])
    return {"status": P.PASS if ok else P.FAIL, "codes": codes, "source": "synthetic fixture",
            "detail": {"challenges": l.get("challenges")}, "consistent": bool(l.get("frames_consistent", True))}


def virtual_camera(labels: list[str]) -> bool:
    return any(t in (l or "").lower() for l in labels for t in VIRTUAL_TOKENS)


def simulated_voice(app_id: str, reg_sim: float) -> float:
    """SIMULATED speaker check: correlated with the registry face result + deterministic noise.
    Not class-conditional on the label, so it can't leak ground truth into the demo."""
    noise = int(hashlib.md5(app_id.encode()).hexdigest()[:6], 16) / 0xFFFFFF - 0.5
    base = 0.85 if (not np.isnan(reg_sim) and reg_sim > F.threshold()) else 0.3
    return float(np.clip(base + 0.25 * noise, 0, 1))


def _face_status(a, b, sim, thr, other_available=True):
    if not other_available:
        return P.UNAVAILABLE
    if a is None or b is None:
        return P.UNAVAILABLE  # no face to compare: unknown, never a pass
    return P.PASS if sim >= thr else P.FAIL


def assess(ext: dict, registry_emb, live: dict, camera_labels: list[str], reuse: dict,
           registry_face_url: str | None = None, active_camera: str | None = None,
           registry_available: bool = True) -> ModuleResult:
    """live: result of verify_challenge / not_provided / challenge_rejected / fixture_liveness."""
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
    f["ev_face_card"] = P.CODE[_face_status(se, ce, f["bio_sim_card"], thr)]
    f["ev_face_registry"] = P.CODE[_face_status(se, registry_emb, f["bio_sim_registry"], thr, registry_available)]

    f["bio_face_reuse_diff_name"] = float(reuse.get("diff_name", 0))
    f["bio_face_reuse_max_sim"] = float(reuse.get("max_sim", 0))
    if reuse.get("diff_name", 0) > 0:
        R.append(reason("BIO_FACE_REUSED", 0.5))
    # the same picture submitted before: a live camera never produces the same frame twice
    f["bio_media_reuse"] = float(reuse.get("media", 0))
    if f["bio_media_reuse"] > 0:
        R.append(reason("BIO_MEDIA_REUSED", 0.4))
    f["meta_genai_selfie"] = float(bool(ext.get("genai_marker")))
    if ext.get("genai_marker"):
        R.append(reason("BIO_GENAI_METADATA", 0.5))

    # client-reported hint only: judge the camera actually streaming (an installed-but-unused OBS is not an injection)
    labels = [active_camera] if active_camera else [l for l in camera_labels or [] if l]
    vc = virtual_camera(labels)
    f["bio_virtual_cam"] = float(vc)
    f["ev_camera_hint"] = P.CODE[P.FAIL if vc else (P.PASS if labels else P.NOT_PROVIDED)]
    if vc:
        R.append(reason("BIO_VIRTUAL_CAMERA", 0.6))

    st = live["status"]
    f["ev_liveness"] = P.CODE[st]
    f["bio_liveness_pass"] = 1.0 if st == P.PASS else (0.0 if st == P.FAIL else np.nan)
    f["bio_frames_consistent"] = np.nan if live.get("consistent") is None else float(live["consistent"])
    for c in live.get("codes", []):
        R.append(reason(c, 0.5 if st == P.FAIL else 0.0))

    p = ext["passive"]
    f["bio_blur"], f["bio_moire"] = p["blur"], p["moire"]
    if p["moire"] > 160:  # genuine-selfie p99 on the train split; blur didn't separate replay from genuine
        R.append(reason("BIO_SCREEN_REPLAY", 0.2))

    hard = 1.0 if (vc or st == P.FAIL) else 0.0
    s = 0.0
    for v, w in ((f["bio_sim_card"], .3), (f["bio_sim_registry"], .45)):
        s += w * (1.0 if np.isnan(v) else float(np.clip((thr + 0.15 - v) / 0.3, 0, 1)))
    s += 0.25 * min(1, f["bio_face_reuse_diff_name"])
    risk = max(hard * 0.9, min(1, s))
    f["bio_risk"] = risk
    return ModuleResult(module="biometric", risk=round(risk, 3), reasons=R, features=f,
                        latency_ms=int((time.time() - t0) * 1000),
                        evidence={"threshold": thr, "sim_card": f["bio_sim_card"], "sim_registry": f["bio_sim_registry"],
                                  "liveness": live, "passive": p, "reuse": reuse, "camera": labels,
                                  "registry_face_url": registry_face_url})
