"""Make a genuine DEMO identity card for a person, from a passport-style photo, and enrol them in the demo registries.

The card is TrueID's fictional "Union Identity Authority" SPECIMEN format, signed with THIS machine's demo issuer key.
It is not, and does not look like, an Aadhaar card: use it only with this project's KYC flow and partner sites.

    # one person, from the command line
    .venv/Scripts/python.exe scripts/make_person_card.py --photo me.jpg --name "Vauldan D'Souza" --dob 12/06/2004 \
        --gender M --address "Hostel Block A, NIT Goa, Cuncolim" --pincode 403703
    # a person committed under demo/people/<slug>/ (photo.jpg + person.json), or all of them
    .venv/Scripts/python.exe scripts/make_person_card.py --from demo/people/vauldan-d-souza
    .venv/Scripts/python.exe scripts/make_person_card.py --all

Writes data/generated/people/<slug>/ (git-ignored): card.jpg, portrait.jpg and details.json (what to type in the
KYC form). Enrols the person in the demo identity, tax, telecom, CKYC and credit registries so every required check can
pass, and (unless --no-footprint) gives them a consistent simulated digital footprint for the optional footprint check.
Restart the backend afterwards so the registries reload. Values you don't give are generated (and say so), and the
same person always gets the same generated values.

Cards must be made on the machine that checks them: the QR is signed with that machine's issuer key, which is never
committed. That is why demo/people/ holds the inputs (photo and details), not a card to reuse.
"""
import argparse
import json
import random
import re
import string
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import GEN  # noqa: E402
from app.demo_kit import _payload, _portrait  # noqa: E402
from app.modules.biometric.face import embed  # noqa: E402
from app.modules.document import card as C  # noqa: E402
from app.modules.document.checksums import pan_valid, verhoeff_digit  # noqa: E402
from app.modules.document.qr_sign import make_qr_text  # noqa: E402
from app.modules.registry import mocks  # noqa: E402

PEOPLE = ROOT / "demo" / "people"
FIELDS = ("name", "dob", "gender", "address", "pincode", "phone", "email", "id_number", "pan", "issue_date")


def build(p: dict, photo: Path, footprint: bool = True) -> dict:
    """p: the person's details (missing ones are generated). Returns what to type in the KYC form."""
    p = {k: (p.get(k) or "") for k in FIELDS}
    p["issue_date"] = p["issue_date"] or "05/07/2022"
    datetime.strptime(p["dob"], "%d/%m/%Y")
    datetime.strptime(p["issue_date"], "%d/%m/%Y")
    if p["gender"] not in ("M", "F"):
        sys.exit(f"{p['name']}: gender must be M or F")
    img = cv2.imread(str(photo))
    if img is None:
        sys.exit(f"can't read {photo}")
    face = embed(img)
    if face is None:
        sys.exit(f"{photo}: no face found; use a clear, front-facing photo")

    rnd = random.Random(p["name"] + p["dob"])  # the same person gets the same generated values on a re-run
    generated = []
    surname = re.sub(r"[^A-Za-z]", "", p["name"].split()[-1]) or "X"
    if not p["id_number"]:
        n11 = str(rnd.randint(2, 9)) + "".join(rnd.choice(string.digits) for _ in range(10))
        p["id_number"] = n11 + verhoeff_digit(n11)
        generated.append("id_number")
    if not p["pan"]:
        p["pan"] = "".join(rnd.choice(string.ascii_uppercase) for _ in range(3)) + "P" + surname[0].upper() + \
            f"{rnd.randint(0, 9999):04d}" + rnd.choice(string.ascii_uppercase)
        generated.append("pan")
    if not p["phone"]:
        p["phone"] = rnd.choice("6789") + "".join(rnd.choice(string.digits) for _ in range(9))
        generated.append("phone")
    if not p["email"]:
        p["email"] = re.sub(r"[^a-z]", ".", p["name"].lower()).strip(".") + "@gmail.com"
        generated.append("email")
    ok, why = pan_valid(p["pan"], surname)
    if not ok:
        sys.exit(f"PAN {p['pan']} is not valid for surname {surname}: {why}")

    slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-")
    out = GEN / "people" / slug
    out.mkdir(parents=True, exist_ok=True)
    portrait = _portrait(img)
    portrait.save(out / "portrait.jpg", quality=92)

    reg = mocks.db()
    today = date.today()
    reg["uidai"][p["id_number"]] = {"name": p["name"], "dob": p["dob"], "gender": p["gender"],
                                    "face": str((out / "portrait.jpg").relative_to(GEN)).replace("\\", "/")}
    reg["pan"][p["pan"]] = {"name": p["name"], "dob": p["dob"], "subject": p["id_number"]}
    reg["telecom"][p["phone"]] = {"activated": (today - timedelta(days=1800)).strftime("%d/%m/%Y"), "subscriber": p["name"]}
    reg["ckyc"][p["id_number"]] = {"first_seen": (today - timedelta(days=1200)).strftime("%d/%m/%Y")}
    reg["bureau"][p["id_number"]] = {"accounts": 2, "oldest_months": 30, "inquiries_90d": 0}
    (GEN / "registry.json").write_text(json.dumps(reg))
    if footprint:
        add_footprint(p, face["emb"], slug, today)

    C.render(p, portrait, make_qr_text(_payload(p))).save(out / "card.jpg", quality=95)
    details = {**p, "generated": generated,
               "note": "Demo SPECIMEN card for TrueID tests only. Type these values in the KYC form; take a live selfie."}
    (out / "details.json").write_text(json.dumps(details, indent=2))
    print(json.dumps({"folder": str(out), **details}, indent=2))
    return details


def add_footprint(p: dict, emb, slug: str, today: date):
    """Simulated, consistent footprint (app/modules/footprint): what a licensed provider would return for this person."""
    import numpy as np
    fp_path, ph_path = GEN / "footprint.json", GEN / "footprint_photos.npz"
    fp = json.loads(fp_path.read_text()) if fp_path.exists() else {"email": {}, "phone": {}, "linked": {}, "consent": {}}
    photos = dict(np.load(ph_path)) if ph_path.exists() else {}
    key = f"person_{slug}"
    photos[key] = emb
    fp["email"][p["email"].lower()] = {"first_seen": (today - timedelta(days=2200)).isoformat(), "services": 9}
    fp["phone"][p["phone"]] = {"first_seen": (today - timedelta(days=1800)).isoformat(), "services": 6}
    fp["linked"][p["email"].lower()] = {"provider": "google", "name": p["name"],
                                        "created": (today - timedelta(days=2100)).isoformat(), "photo": key}
    fp_path.write_text(json.dumps(fp))
    np.savez(ph_path, **photos)


def from_folder(d: Path, footprint: bool) -> dict:
    spec = json.loads((d / "person.json").read_text())
    return build(spec, d / spec.get("photo", "photo.jpg"), footprint)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--photo", help="passport-style photo, face clearly visible (then give --name, --dob, --gender)")
    src.add_argument("--from", dest="folder", help="a folder with photo.jpg and person.json (e.g. demo/people/<slug>)")
    src.add_argument("--all", action="store_true", help="every person under demo/people/")
    ap.add_argument("--name")
    ap.add_argument("--dob", help="DD/MM/YYYY")
    ap.add_argument("--gender", choices=["M", "F"])
    ap.add_argument("--address", default="")
    ap.add_argument("--pincode", default="")
    ap.add_argument("--phone", help="10 digits; generated if omitted")
    ap.add_argument("--email", help="generated from the name if omitted")
    ap.add_argument("--id-number", help="12 digits with a valid check digit; generated if omitted")
    ap.add_argument("--pan", help="generated (format-valid for the surname) if omitted")
    ap.add_argument("--issue-date", default="05/07/2022", help="DD/MM/YYYY")
    ap.add_argument("--no-footprint", action="store_true",
                    help="don't add a simulated digital footprint (old email + a linked account in their name and face)")
    a = ap.parse_args()
    fp = not a.no_footprint
    if a.all:
        folders = sorted(d for d in PEOPLE.glob("*") if (d / "person.json").exists())
        for d in folders:
            from_folder(d, fp)
        print(f"Made {len(folders)} demo card(s).")
    elif a.folder:
        from_folder(Path(a.folder), fp)
    else:
        if not (a.name and a.dob and a.gender):
            ap.error("--photo needs --name, --dob and --gender")
        build({k: getattr(a, k) for k in FIELDS}, Path(a.photo), fp)
    print("Restart the TrueID backend so the demo registries reload.")


if __name__ == "__main__":
    main()
