"""Enrol Kestrel's four test people in TrueID's mock government registries, so the home-loan site works end to end
in connected mode: PAN (NSDL), Aadhaar (UIDAI, with a registry photo), telecom (an old SIM), CKYC and credit bureau.

    cd backend
    ../.venv/Scripts/python.exe ../clients/kyc-homeloan/tools/enrol_in_trueid.py --photo C:/path/to/your_face.jpg [--as riya-kamat]

--photo is a clear, front-facing photo of YOU. It becomes the UIDAI registry photo and the ID-card portrait of the
person named by --as (default: Riya Kamat), so your live selfie can match both and TrueID can approve that person.
The other three people are enrolled without a face (their face checks come back "unavailable", so they go to review).

Run it AFTER TrueID's build (the build rewrites data/generated/registry.json), then restart the TrueID backend:
the registries are loaded once at startup. It also regenerates clients/kyc-homeloan/public/test-documents so the
cards carry the same portrait and are signed with this machine's issuer key.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import cv2
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "backend"))
sys.path.insert(0, str(HERE))

from app.config import GEN  # noqa: E402
import make_test_docs as docs  # noqa: E402


def portrait_from(photo: Path) -> Image.Image:
    """Square crop of the centre, the way TrueID's presenter kit does it (app/demo_kit.py)."""
    img = cv2.imread(str(photo))
    if img is None:
        sys.exit(f"Could not read {photo}")
    h, w = img.shape[:2]
    side = min(h, w)
    crop = img[(h - side) // 2:(h + side) // 2, (w - side) // 2:(w + side) // 2]
    crop = cv2.resize(crop, (250, 250))[:, 25:225]
    return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", type=Path, help="a clear front-facing photo of you")
    ap.add_argument("--as", dest="who", default="riya-kamat", help="whose identity gets your face (slug, e.g. riya-kamat)")
    a = ap.parse_args()
    slugs = {p["name"].lower().replace(" ", "-"): p for p in docs.PEOPLE}
    if a.who not in slugs:
        sys.exit(f"--as must be one of {', '.join(slugs)}")

    path = GEN / "registry.json"
    if path.exists():
        reg = json.loads(path.read_text())
    else:
        print("! No registry.json yet: TrueID's build has not run. Enrolling into an empty registry; the build will "
              "overwrite it, so run this script again after the build.")
        GEN.mkdir(parents=True, exist_ok=True)
        reg = {"uidai": {}, "pan": {}, "telecom": {}, "ckyc": {}, "bureau": {}}

    faces = GEN / "partner_test"
    faces.mkdir(parents=True, exist_ok=True)
    blank = Image.new("RGB", (200, 250), (226, 232, 240))  # no face: TrueID reports the registry face as unavailable
    portraits = {}
    me = portrait_from(a.photo) if a.photo else None
    today = date.today()
    for slug, p in slugs.items():
        face = me if (me is not None and slug == a.who) else None
        portraits[slug] = face
        fpath = faces / f"{slug}.jpg"
        (face or blank).save(fpath, quality=92)
        name = p["name"].upper()
        reg["uidai"][p["id_number"]] = {"name": name, "dob": p["dob"], "gender": p["gender"],
                                        "face": str(fpath.relative_to(GEN)).replace("\\", "/"),
                                        "address": f"{p['address']} {p['pin']}"}
        reg["pan"][p["pan"]] = {"name": name, "dob": p["dob"], "subject": p["id_number"]}
        reg["telecom"][docs_phone(p)] = {"activated": (today - timedelta(days=2200)).strftime("%d/%m/%Y"), "subscriber": name}
        reg["ckyc"][p["id_number"]] = {"first_seen": (today - timedelta(days=1500)).strftime("%d/%m/%Y")}
        reg["bureau"][p["id_number"]] = {"accounts": 3, "oldest_months": 60, "inquiries_90d": 1}
    path.write_text(json.dumps(reg))

    docs.generate(portraits)
    print(f"Enrolled {len(slugs)} people in {path}")
    print(f"  {slugs[a.who]['name']}: " + ("your photo is the UIDAI photo and the card portrait" if me is not None
                                           else "no photo given: face checks will be unavailable"))
    print("Next: restart the TrueID backend (registries load at startup), then run scripts/check_partner_connection.py")


PHONES = {"234567890124": "9822001122", "345678901238": "9890456712", "456789012341": "9765123480", "567890123458": "9923345671"}


def docs_phone(p: dict) -> str:
    """Mobile numbers match DEMO_IDENTITIES in clients/*/server.js."""
    return PHONES[p["id_number"]]


if __name__ == "__main__":
    main()
