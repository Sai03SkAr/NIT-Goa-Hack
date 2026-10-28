"""Checks every link between a partner site (default: Kestrel Home Finance) and TrueID Shield, and says how to fix
what is broken. Standard library only.

    python scripts/check_partner_connection.py
    python scripts/check_partner_connection.py --site http://localhost:3013 --api http://127.0.0.1:8000 --key kh_test_3e8d14b9c702
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RIYA = {"pan": "ABCPK1234Z", "id_number": "234567890124", "name": "RIYA KAMAT"}


def call(url, key=None, method="GET", body=None, ctype=None, timeout=60):
    req = urllib.request.Request(url, data=body, method=method)
    if key:
        req.add_header("X-Partner-Key", key)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except json.JSONDecodeError:
            return e.code, None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, str(getattr(e, "reason", e))


def multipart(fields: dict, file_field: str, path: Path) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{b}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
            f'Content-Type: image/jpeg\r\n\r\n').encode() + path.read_bytes() + b"\r\n" + f"--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="http://localhost:3013")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--key", default="kh_test_3e8d14b9c702", help="the partner key in backend/app/partners.py")
    a = ap.parse_args()
    api, site, key = a.api.rstrip("/"), a.site.rstrip("/"), a.key
    rows = []

    def check(name, ok, detail="", fix=""):
        rows.append((name, ok, detail, fix))

    s, j = call(f"{api}/api/health")
    check("TrueID backend is running", s == 200, f"model: {j.get('model')}" if s == 200 else str(j),
          "Start it: cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000")
    if s == 200:
        check("TrueID fraud model is built", j.get("model") not in ("unavailable", None), f"model: {j.get('model')}",
              "Run the build (docs/PARTNER_INTEGRATION.md step 3). Until then every case goes to REVIEW.")

    s1, _ = call(f"{api}/api/partner/v1/analytics")
    s2, j2 = call(f"{api}/api/partner/v1/analytics", key)
    check("Partner key is accepted (and required)", s1 == 401 and s2 == 200,
          f"no key -> {s1}, with key -> {s2} ({(j2 or {}).get('partner', '') if isinstance(j2, dict) else j2})",
          "Use the key from backend/app/partners.py, or the one set in TRUEID_PARTNER_KEYS, in the site's .env.local")

    s, j = call(f"{api}/api/partner/v1/registry/pan/{RIYA['pan']}", key)
    check("Test people are enrolled in TrueID's registries", s == 200,
          f"PAN {RIYA['pan']} -> {s} {j.get('name', '') if isinstance(j, dict) else ''}" if s else str(j),
          "503: build TrueID first. 404: run clients/kyc-homeloan/tools/enrol_in_trueid.py, then restart TrueID.")
    s, j = call(f"{api}/api/partner/v1/registry/pan-link?pan={RIYA['pan']}&id_number={RIYA['id_number']}", key)
    check("PAN-Aadhaar link check", s == 200 and j.get("linked") is True, f"{s} {j}", "Same fix as the line above.")

    s, j = call(f"{api}/api/partner/v1/liveness/challenge", key, method="POST")
    check("Liveness challenges are issued", s == 200 and bool((j or {}).get("challenge_id")),
          f"sequence {j.get('sequence')}, valid {j.get('expires_in')} s" if s == 200 else f"{s} {j}")

    bill = ROOT / "clients/kyc-homeloan/public/test-documents/riya-kamat/electricity-bill.jpg"
    if bill.exists():
        body, ct = multipart({"kind": "electricity_bill", "owner": "Riya Kamat", "claims": json.dumps({"name": "Riya Kamat"})}, "file", bill)
        s, j = call(f"{api}/api/partner/v1/documents/check", key, "POST", body, ct, timeout=120)
        ok = s == 200 and isinstance(j, dict) and j.get("checks")
        check("Document checks answer", bool(ok), f"{len(j['checks'])} checks returned" if ok else f"{s} {j}")
        if ok:
            ocr = next((c for c in j["checks"] if c["check"] == "text_name"), {})
            check("Text reading (OCR) is ready", ocr.get("status") == "PASS", f"name on the bill: {ocr.get('status')} {ocr.get('detail', '')}",
                  "EasyOCR downloads its models on first use; pre-download them (docs/PARTNER_INTEGRATION.md step 2).")
    else:
        check("Document checks answer", False, f"{bill} missing", "Run clients/kyc-homeloan/tools/make_test_docs.py")

    s, j = call(f"{site}/api/mode")
    check("Site is running", s == 200, f"{site} -> {s}", f"Start it: cd clients/kyc-homeloan && node server.js")
    if s == 200:
        check("Site is connected to TrueID (not demo mode)", j.get("mode") == "remote", f"mode: {j.get('mode')}, backend: {j.get('backend')}",
              "Set TRUEID_MODE=remote (or auto) and TRUEID_API_URL in clients/kyc-homeloan/.env.local, restart the site")
        s, j = call(f"{site}/api/verify/pan", method="POST", body=json.dumps({"pan": RIYA["pan"], "dob": "04/09/1999"}).encode(), ctype="application/json")
        check("Site verifies a PAN through TrueID", s == 200 and j.get("ok") is True, f"{j}", "See the enrolment line above.")

    width = max(len(r[0]) for r in rows)
    for name, ok, detail, fix in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
        if not ok and fix:
            print(f"      fix: {fix}")
    bad = sum(not r[1] for r in rows)
    print(f"\n{len(rows) - bad}/{len(rows)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
