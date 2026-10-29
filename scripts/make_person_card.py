"""Make a genuine DEMO identity card for one person, from a passport-style photo, and enrol them in the demo registries.

The card is TrueID's fictional "Union Identity Authority" SPECIMEN format, signed with the local demo issuer key. It
is not, and does not look like, an Aadhaar card: use it only with this project's KYC flow and partner sites.

    .venv/Scripts/python.exe scripts/make_person_card.py --photo me.jpg --name "Vauldan D'Souza" --dob 12/06/2004 \
        --gender M --address "Hostel Block A, NIT Goa, Cuncolim" --pincode 403703

Writes data/generated/people/<slug>/ (git-ignored): card.jpg, portrait.jpg and details.json (what to type in the
KYC form). Enrols the person in the demo identity, tax, telecom, CKYC and credit registries so every required check can
pass, and (unless --no-footprint) gives them a consistent simulated digital footprint for the optional footprint check. Restart the backend afterwards so the registries reload. Values you don't give are generated (and say so).
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import GEN  # noqa: E402
from app.demo_kit import _payload, _portrait  # noqa: E402
from app.modules.biometric.face import embed  # noqa: E402
from app.modules.document import card as C  # noqa: E402
from app.modules.document.checksums import pan_valid, verhoeff_digit  # noqa: E402
from app.modules.document.qr_sign import make_qr_text  # noqa: E402
from app.modules.registry import mocks  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photo", required=True, help="passport-style photo, face clearly visible")
    ap.add_argument("--name", required=True)
    ap.add_argument("--dob", required=True, help="DD/MM/YYYY")
    ap.add_argument("--gender", choices=["M", "F"], required=True)
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

    datetime.strptime(a.dob, "%d/%m/%Y")
    datetime.strptime(a.issue_date, "%d/%m/%Y")
    img = cv2.imread(a.photo)
    if img is None:
        sys.exit(f"can't read {a.photo}")
    face = embed(img)
    if face is None:
        sys.exit("no face found in the photo: use a clear, front-facing photo")

    rnd = random.Random(a.name + a.dob)  # the same person gets the same generated values on a re-run
    generated = []
    surname = re.sub(r"[^A-Za-z]", "", a.name.split()[-1]) or "X"
    if not a.id_number:
        n11 = str(rnd.randint(2, 9)) + "".join(rnd.choice(string.digits) for _ in range(10))
        a.id_number = n11 + verhoeff_digit(n11)
        generated.append("id_number")
    if not a.pan:
        a.pan = "".join(rnd.choice(string.ascii_uppercase) for _ in range(3)) + "P" + surname[0].upper() + \
            f"{rnd.randint(0, 9999):04d}" + rnd.choice(string.ascii_uppercase)
        generated.append("pan")
    if not a.phone:
        a.phone = rnd.choice("6789") + "".join(rnd.choice(string.digits) for _ in range(9))
        generated.append("phone")
    if not a.email:
        a.email = re.sub(r"[^a-z]", ".", a.name.lower()).strip(".") + "@gmail.com"
        generated.append("email")
    ok, why = pan_valid(a.pan, surname)
    if not ok:
        sys.exit(f"PAN {a.pan} is not valid for surname {surname}: {why}")

    person = {"name": a.name, "dob": a.dob, "gender": a.gender, "id_number": a.id_number, "issue_date": a.issue_date,
              "pan": a.pan, "phone": a.phone, "email": a.email, "address": a.address, "pincode": a.pincode}
    slug = re.sub(r"[^a-z0-9]+", "-", a.name.lower()).strip("-")
    out = GEN / "people" / slug
    out.mkdir(parents=True, exist_ok=True)
    portrait = _portrait(img)
    portrait.save(out / "portrait.jpg", quality=92)

    reg = mocks.db()
    today = date.today()
    reg["uidai"][a.id_number] = {"name": a.name, "dob": a.dob, "gender": a.gender,
                                 "face": str((out / "portrait.jpg").relative_to(GEN)).replace("\\", "/")}
    reg["pan"][a.pan] = {"name": a.name, "dob": a.dob, "subject": a.id_number}
    reg["telecom"][a.phone] = {"activated": (today - timedelta(days=1800)).strftime("%d/%m/%Y"), "subscriber": a.name}
    reg["ckyc"][a.id_number] = {"first_seen": (today - timedelta(days=1200)).strftime("%d/%m/%Y")}
    reg["bureau"][a.id_number] = {"accounts": 2, "oldest_months": 30, "inquiries_90d": 0}
    (GEN / "registry.json").write_text(json.dumps(reg))

    if not a.no_footprint:
        add_footprint(person, face["emb"], slug, today)

    card = C.render(person, portrait, make_qr_text(_payload(person)))
    card.save(out / "card.jpg", quality=95)
    details = {**person, "generated": generated,
               "note": "Demo SPECIMEN card for TrueID tests only. Type these values in the KYC form; take a live selfie."}
    (out / "details.json").write_text(json.dumps(details, indent=2))
    print(json.dumps({"folder": str(out), **details}, indent=2))
    print("Restart the TrueID backend so the demo registries reload.")


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


if __name__ == "__main__":
    main()
