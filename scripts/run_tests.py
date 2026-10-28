"""End-to-end acceptance test: builds a fresh test kit on the running backend, submits every scenario through
/api/apply exactly like the browser does (applicant session, consent, server-issued liveness challenge), polls the
job, and checks the decision against the expectation.

Liveness is answered with FIXTURE PHOTOS of the same person (frontal, turned, mirrored), verified server-side like
webcam frames. This exercises the real protocol; it is not a live camera session.

Run (backend must be up):  .venv/bin/python scripts/run_tests.py   [--encrypted 10: genuine people with encrypted QR cards]
Analyst key: TRUEID_ANALYST_KEY or backend/.secrets/analyst_key.
Writes a report to data/generated/testkit/<tag>/REPORT.md. Exit code 1 if any scenario fails."""
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

import httpx

API = os.getenv("TRUEID_API", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[1]


def analyst_key() -> str:
    k = os.getenv("TRUEID_ANALYST_KEY")
    if k:
        return k
    return (ROOT / "backend" / ".secrets" / "analyst_key").read_text().strip()


def signals(kind: str, seed: str) -> dict:
    r = random.Random(seed)
    if kind == "bot":
        return {"fill_time": 7.2, "iki_mean": 36, "iki_std": 2.1, "paste_fields": 7, "corrections": 0, "blur_count": 0,
                "mouse_entropy": 0.4, "keystroke_vec": [2.5] * 12}
    vec_seed = "ring" if kind == "ring" else seed  # one fraudster typing every ring identity has one rhythm
    v = random.Random(vec_seed)
    return {"fill_time": round(r.uniform(55, 110), 1), "iki_mean": round(r.uniform(160, 220), 1),
            "iki_std": round(r.uniform(55, 80), 1), "paste_fields": r.choice([0, 0, 1]), "corrections": r.randint(1, 5),
            "blur_count": r.randint(0, 1), "mouse_entropy": round(r.uniform(3.0, 3.9), 2),
            "keystroke_vec": [round(v.gauss(0, 1), 3) for _ in range(12)]}


def run_one(c: httpx.Client, s: dict, tag: str, consent_version: str) -> dict:
    card, selfie = c.get(API + s["card"]).content, c.get(API + s["selfie"]).content
    ch = c.post(API + "/api/liveness/challenge").json()
    order = ["neutral", *ch["sequence"]]
    frames = [("frames", (f"{k}.jpg", c.get(API + s["frames"][k]).content, "image/jpeg")) for k in order]
    payload = {"form": s["form"], "challenge_id": ch["challenge_id"],
               "consent": {"accepted": True, "version": consent_version},
               "device": {"device_id": s["device_id"], "user_agent": "scripts/run_tests.py",
                          "camera_labels": [s["camera"]], "active_camera": s["camera"]},
               "telemetry": signals(s["signals"], s["id"] + tag)}
    r = c.post(API + "/api/apply", data={"payload": json.dumps(payload)}, headers={"Idempotency-Key": uuid.uuid4().hex},
               files=[("card", ("card.jpg", card, "image/jpeg")), ("selfie", ("selfie.jpg", selfie, "image/jpeg")), *frames])
    r.raise_for_status()
    app_id = r.json()["app_id"]
    after, t0 = 0, time.time()
    while True:
        ev = c.get(f"{API}/api/apply/{app_id}/events", params={"after": after}).json()
        if any(e.get("node") == "error" for e in ev["events"]):
            raise RuntimeError(f"{s['id']}: pipeline error {ev['events']}")
        after = ev["next"]
        if ev["done"]:
            break
        if time.time() - t0 > 180:
            raise TimeoutError(s["id"])
        time.sleep(0.5)
    case = c.get(f"{API}/api/apps/{app_id}").json()
    codes = [x["code"] for m in case["modules"] for x in m["reasons"] if x["weight"] > 0]
    live = next((m["evidence"].get("liveness", {}) for m in case["modules"] if m["module"] == "biometric"), {})
    return {"app_id": app_id, "band": case["band"], "prob": case["prob"], "pattern": case["fraud_label"],
            "rules": case["rule_codes"], "codes": codes, "liveness": live.get("status")}


def fmt(p):
    return "n/a " if p is None else f"{p:.2f}"


def main() -> int:
    with httpx.Client(timeout=120) as c:
        try:
            c.get(API + "/api/health").raise_for_status()
        except Exception:
            print("Backend not reachable at", API, "- start it with ./scripts/run_backend.sh")
            return 2
        c.post(API + "/api/auth/login", json={"key": analyst_key()}).raise_for_status()
        consent_version = c.post(API + "/api/session").json()["consent_version"]
        enc = int(sys.argv[sys.argv.index("--encrypted") + 1]) if "--encrypted" in sys.argv else 0
        kit = c.post(API + "/api/testkit", params={"encrypted": enc}, timeout=1200).json()  # finds unseen faces with usable head turns: minutes on CPU
        print(f"Test kit {kit['tag']}: {len(kit['scenarios'])} scenarios -> {kit['folder']}\n")
        rows, failed = [], 0
        for s in kit["scenarios"]:
            res = run_one(c, s, kit["tag"], consent_version)
            ok = res["band"] in s["expect"]
            failed += not ok
            rows.append((s, res, ok))
            print(f"{'PASS' if ok else 'FAIL'}  {s['id']:<20} expected {'/'.join(s['expect']):<14} got {res['band']:<8}"
                  f" p={fmt(res['prob'])}  liveness={res['liveness']:<12} {res['pattern']:<26} {', '.join(res['codes'][:4])}")
    lines = [f"# Test report, kit {kit['tag']}", "", f"{len(rows) - failed}/{len(rows)} scenarios behaved as expected.", "",
             "Liveness answered with fixture photos of the same person, verified server-side (not a live camera).", "",
             "| Result | Scenario | Expected | Got | p(fraud) | Liveness | Pattern | Top signals | Case |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s, r, ok in rows:
        lines.append(f"| {'PASS' if ok else '**FAIL**'} | {s['title']} | {' / '.join(s['expect'])} | {r['band']} | {fmt(r['prob'])} | "
                     f"{r['liveness']} | {r['pattern']} | {', '.join(r['codes'][:4]) or '-'} | {r['app_id']} |")
    Path(kit["folder"], "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(rows) - failed}/{len(rows)} passed. Report: {kit['folder']}/REPORT.md")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
