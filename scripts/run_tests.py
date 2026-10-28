"""End-to-end acceptance test: builds a fresh test kit on the running backend, submits every scenario through
/api/apply exactly like the browser does, waits for the pipeline, and checks the decision against the expectation.

Run (backend must be up):  .venv/bin/python scripts/run_tests.py
Writes a report to data/generated/testkit/<tag>/REPORT.md. Exit code 1 if any scenario fails."""
import json
import random
import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000"


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


def run_one(c: httpx.Client, s: dict, tag: str) -> dict:
    card, selfie = c.get(API + s["card"]).content, c.get(API + s["selfie"]).content
    payload = {"form": s["form"], "source": "test",
               "device": {"device_id": s["device_id"], "user_agent": "scripts/run_tests.py",
                          "camera_labels": [s["camera"]], "active_camera": s["camera"]},
               "telemetry": signals(s["signals"], s["id"] + tag),
               "liveness": {"challenges": ["turn_left", "blink"], "passed": s["liveness_passed"],
                            "virtual_camera": "virtual" in s["camera"].lower()}}
    r = c.post(API + "/api/apply", data={"payload": json.dumps(payload)},
               files={"card": ("card.jpg", card, "image/jpeg"), "selfie": ("selfie.jpg", selfie, "image/jpeg")})
    r.raise_for_status()
    app_id = r.json()["app_id"]
    with c.stream("GET", f"{API}/api/apply/{app_id}/events", timeout=120) as st:
        for line in st.iter_lines():
            if line.startswith("data:") and '"error"' in line:
                raise RuntimeError(line)
    case = c.get(f"{API}/api/apps/{app_id}").json()
    codes = [x["code"] for m in case["modules"] for x in m["reasons"] if x["weight"] > 0]
    return {"app_id": app_id, "band": case["band"], "prob": case["prob"], "pattern": case["fraud_label"],
            "rules": case["rule_codes"], "codes": codes}


def main() -> int:
    with httpx.Client(timeout=120) as c:
        try:
            c.get(API + "/api/health").raise_for_status()
        except Exception:
            print("Backend not reachable at", API, "- start it with ./scripts/run_backend.sh")
            return 2
        kit = c.post(API + "/api/testkit", timeout=300).json()
        print(f"Test kit {kit['tag']}: {len(kit['scenarios'])} scenarios -> {kit['folder']}\n")
        rows, failed = [], 0
        for s in kit["scenarios"]:
            res = run_one(c, s, kit["tag"])
            ok = res["band"] in s["expect"]
            failed += not ok
            rows.append((s, res, ok))
            print(f"{'PASS' if ok else 'FAIL'}  {s['id']:<20} expected {'/'.join(s['expect']):<14} got {res['band']:<8}"
                  f" p={res['prob']:.2f}  {res['pattern']:<28} {', '.join(res['codes'][:4])}")
    lines = [f"# Test report — kit {kit['tag']}", "", f"{len(rows) - failed}/{len(rows)} scenarios behaved as expected.", "",
             "| Result | Scenario | Expected | Got | p(fraud) | Pattern | Top signals | Case |", "|---|---|---|---|---|---|---|---|"]
    for s, r, ok in rows:
        lines.append(f"| {'PASS' if ok else '**FAIL**'} | {s['title']} | {' / '.join(s['expect'])} | {r['band']} | {r['prob']:.2f} | "
                     f"{r['pattern']} | {', '.join(r['codes'][:4]) or '—'} | {r['app_id']} |")
    Path(kit["folder"], "REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(rows) - failed}/{len(rows)} passed. Report: {kit['folder']}/REPORT.md")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
