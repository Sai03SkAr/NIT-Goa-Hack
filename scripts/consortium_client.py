"""Reference client for the cross-institution fraud network (backend/app/consortium.py). Standard library only.

A member bank hashes identifiers LOCALLY with the consortium key and sends only the tokens, so no customer data
leaves the bank. The hashing below must stay identical to app/consortium.py (a test checks it).

    python scripts/consortium_client.py check  --id 234567890124 --name "Riya Kamat" --phone 9822001122
    python scripts/consortium_client.py report --id 234567890124 --name "Riya Kamat" --outcome REJECT --ref CASE-17

Options: --api (default http://127.0.0.1:8000), --partner-key (the member's X-Partner-Key), --key-file (the shared
consortium key; default backend/.secrets/consortium_key, or set TRUEID_CONSORTIUM_KEY).
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- name normalisation: same as backend/app/modules/correlation/fuzzy.py ---------------------------------------------
ALIASES = {"MOHD": "MOHAMMED", "MD": "MOHAMMED", "MOHAMMAD": "MOHAMMED", "MUHAMMAD": "MOHAMMED",
           "SK": "SHAIKH", "SHEIKH": "SHAIKH", "KUMARI": "KUMARI"}
SWAPS = [("EE", "I"), ("OO", "U"), ("SH", "S"), ("W", "V"), ("AA", "A"), ("TH", "T"), ("PH", "F")]


def _norm_token(t: str) -> str:
    t = ALIASES.get(t, t)
    for a, b in SWAPS:
        t = t.replace(a, b)
    return t.rstrip("A") or t


def _name_tokens(name: str) -> list[str]:
    return [_norm_token(t) for t in re.sub(r"[^A-Z ]", " ", (name or "").upper()).split()]


# --- identifier normalisation + token: same as backend/app/consortium.py ----------------------------------------------
def _norm(kind: str, v) -> str:
    s = str(v or "").strip()
    if kind in ("id_number", "account"):
        return re.sub(r"\D", "", s)
    if kind == "phone":
        return re.sub(r"\D", "", s)[-10:]
    if kind == "pan":
        return s.upper().replace(" ", "")
    if kind == "email":
        return s.lower()
    return s


def token(kind: str, value, key: bytes) -> str:
    n = _norm(kind, value) if kind != "name" else " ".join(sorted(_name_tokens(value)))
    return hmac.new(key, f"{kind}:{n}".encode(), hashlib.sha256).hexdigest()[:40] if n else ""


def load_key(path: str | None) -> bytes:
    if os.getenv("TRUEID_CONSORTIUM_KEY"):
        return os.environ["TRUEID_CONSORTIUM_KEY"].encode()
    p = Path(path) if path else ROOT / "backend/.secrets/consortium_key"
    if not p.exists():
        sys.exit(f"No consortium key at {p}. Start TrueID once (it creates it) or set TRUEID_CONSORTIUM_KEY.")
    return p.read_text().strip().encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["check", "report"])
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--partner-key", default="kh_test_3e8d14b9c702")
    ap.add_argument("--key-file")
    for k in ("id", "pan", "phone", "email", "device", "account", "name", "ref"):
        ap.add_argument(f"--{k}", default="")
    ap.add_argument("--outcome", default="", choices=["", "APPROVE", "REVIEW", "REJECT"])
    a = ap.parse_args()
    key = load_key(a.key_file)
    raw = {"id_number": a.id, "pan": a.pan, "phone": a.phone, "email": a.email, "device": a.device, "account": a.account}
    body = {"tokens": {k: t for k, v in raw.items() if (t := token(k, v, key))}, "name_token": token("name", a.name, key)}
    if a.action == "report":
        body.update(outcome=a.outcome, ref=a.ref)
    print("sending tokens only:", json.dumps(body, indent=1))
    req = urllib.request.Request(f"{a.api.rstrip('/')}/api/partner/v1/consortium/{a.action}", data=json.dumps(body).encode(),
                                 method="POST", headers={"Content-Type": "application/json", "X-Partner-Key": a.partner_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(json.dumps(json.loads(r.read()), indent=1))
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code}: {e.read().decode()[:300]}")


if __name__ == "__main__":
    main()
