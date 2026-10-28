"""Behavior agent (D3): session telemetry, bot signals, velocity windows, sequential emails, keystroke links."""
import time
from datetime import timedelta
from functools import lru_cache

import joblib
import numpy as np

from app.config import MODELS
from app.schemas import ModuleResult, reason

TELE_KEYS = ["fill_time", "iki_mean", "iki_std", "paste_fields", "corrections", "blur_count", "mouse_entropy"]
H1, D1, D7 = timedelta(hours=1), timedelta(days=1), timedelta(days=7)


def tele_vector(t: dict) -> np.ndarray:
    return np.array([np.log1p(t["fill_time"]), t["iki_mean"], t["iki_std"], t["paste_fields"], t["corrections"],
                     t["blur_count"], t["mouse_entropy"]], dtype=np.float32)


@lru_cache(maxsize=1)
def iforest():
    p = MODELS / "behavior_iforest.joblib"
    return joblib.load(p) if p.exists() else None


def assess(app: dict, rec: dict, hist) -> ModuleResult:
    t0 = time.time()
    t, ts, a = app["telemetry"], rec["ts"], rec["attrs"]
    R, f = [], {}
    f["beh_fill_time"] = float(t["fill_time"])
    f["beh_iki_mean"], f["beh_iki_std"] = float(t["iki_mean"]), float(t["iki_std"])
    f["beh_iki_cv"] = float(t["iki_std"] / max(t["iki_mean"], 1))
    f["beh_paste_frac"] = t["paste_fields"] / 7
    f["beh_corrections"], f["beh_blur"], f["beh_mouse_entropy"] = float(t["corrections"]), float(t["blur_count"]), float(t["mouse_entropy"])
    if t["fill_time"] < 20:
        R.append(reason("BEH_FAST_FILL", 0.3))
    if t["paste_fields"] >= 5:
        R.append(reason("BEH_PASTE_HEAVY", 0.25))
    if f["beh_iki_cv"] < 0.15:
        R.append(reason("BEH_ROBOTIC_TIMING", 0.3))

    for attr in ("device", "ip", "phone"):
        f[f"beh_vel_{attr}_1h"] = float(hist.count_window(attr, a[attr], ts, H1))
        f[f"beh_vel_{attr}_24h"] = float(hist.count_window(attr, a[attr], ts, D1))
        f[f"beh_vel_{attr}_7d"] = float(hist.count_window(attr, a[attr], ts, D7))
    f["beh_vel_device_rel"] = (f["beh_vel_device_24h"] + 1) / (f["beh_vel_device_7d"] + 1)
    if f["beh_vel_device_24h"] >= 3:
        R.append(reason("BEH_VELOCITY_DEVICE", 0.3))
    if f["beh_vel_ip_1h"] >= 3:
        R.append(reason("BEH_VELOCITY_IP", 0.15))
    if f["beh_vel_phone_7d"] >= 2:
        R.append(reason("BEH_VELOCITY_PHONE", 0.2))

    f["beh_email_seq"] = float(hist.email_sequence(rec["stem"], rec["num"], rec["name"]))
    if f["beh_email_seq"] > 0:
        R.append(reason("BEH_EMAIL_SEQUENCE", 0.3))
    ks = hist.keystroke_matches(rec["ks"], rec["name"])
    f["beh_ks_links"], f["beh_ks_max_sim"] = float(ks["links"]), ks["max_sim"]
    if ks["links"] > 0:
        R.append(reason("BEH_KEYSTROKE_LINK", 0.25))

    m = iforest()
    anom = float(-m.score_samples(tele_vector(t)[None])[0]) if m is not None else np.nan
    f["beh_anomaly"] = anom
    if m is not None and anom > 0.6:
        R.append(reason("BEH_ANOMALY", 0.2))

    risk = min(1.0, sum(r.weight for r in R))
    f["beh_risk"] = risk
    return ModuleResult(module="behavior", risk=round(risk, 3), reasons=R, features=f,
                        latency_ms=int((time.time() - t0) * 1000),
                        evidence={"telemetry": {k: t[k] for k in TELE_KEYS}, "keystroke_matches": ks["matches"],
                                  "velocity": {k: v for k, v in f.items() if k.startswith("beh_vel")}})
