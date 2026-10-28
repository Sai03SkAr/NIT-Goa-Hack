"""Presenter demo kit: enrol the presenter's face as a registry citizen and print three cards:
genuine (their identity), hero DOB edit (Poisson-blended), Frankenstein (a stolen identity with their portrait)."""
import json
import random
import string
import uuid
from datetime import date, timedelta

import cv2
from PIL import Image

from app.config import GEN
from app.modules.biometric.face import embed
from app.modules.document import card as C
from app.modules.document.checksums import verhoeff_digit
from app.modules.document.qr_sign import make_qr_text
from app.modules.registry import mocks

KIT = GEN / "demo"


def _portrait(img_bgr):
    h, w = img_bgr.shape[:2]
    side = min(h, w)
    crop = img_bgr[(h - side) // 2:(h + side) // 2, (w - side) // 2:(w + side) // 2]
    crop = cv2.resize(crop, (250, 250))[:, 25:225]
    return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))


def _payload(f):
    return {"n": f["name"].upper(), "d": f["dob"], "g": f["gender"], "l4": f["id_number"][-4:], "i": f["issue_date"]}


def build_kit(photo_bgr) -> dict:
    e = embed(photo_bgr)
    if e is None:
        return {"error": "no face found in the photo"}
    KIT.mkdir(exist_ok=True)
    reg = mocks.db()
    tag = uuid.uuid4().hex[:6]
    n11 = str(random.randint(2, 9)) + "".join(random.choice(string.digits) for _ in range(10))
    idn = n11 + verhoeff_digit(n11)
    me = {"name": "Demo Presenter", "dob": "14/03/1998", "gender": "M", "id_number": idn, "issue_date": "02/05/2017",
          "pan": "DEMPP" + f"{random.randint(0, 9999):04d}" + "Z", "phone": "98" + "".join(random.choice(string.digits) for _ in range(8)),
          "email": f"presenter.{tag}@gmail.com", "address": "12, Miramar Road, Panaji", "pincode": "403001"}
    portrait = _portrait(photo_bgr)
    face_path = KIT / f"face_{tag}.jpg"
    portrait.save(face_path, quality=92)
    # enrol as a real citizen with a long, clean history
    reg["uidai"][idn] = {"name": me["name"], "dob": me["dob"], "gender": me["gender"], "face": str(face_path.relative_to(GEN))}
    reg["pan"][me["pan"]] = {"name": me["name"], "dob": me["dob"], "id_last4": idn[-4:]}
    reg["telecom"][me["phone"]] = {"activated": (date.today() - timedelta(days=2400)).strftime("%d/%m/%Y"), "subscriber": me["name"]}
    reg["ckyc"][idn] = {"first_seen": "11/08/2019"}
    reg["bureau"][idn] = {"accounts": 3, "oldest_months": 70, "inquiries_90d": 0}
    mocks._face_cache[idn] = e["emb"]

    genuine = C.render(me, portrait, make_qr_text(_payload(me)))
    genuine.save(KIT / f"genuine_{tag}.jpg", quality=92)
    hero = C.poisson_edit(genuine, "dob", "14/03/1994")
    hero.save(KIT / f"hero_dob_edit_{tag}.jpg", quality=92)

    victim = random.choice(json.loads((GEN / "demo_spares.json").read_text()))
    vf = {k: victim[k] for k in ("name", "dob", "gender", "id_number", "issue_date")}
    frank = C.splice_portrait(C.render(vf, Image.open(GEN / victim["face"]), make_qr_text(_payload(vf))), portrait)
    frank.save(KIT / f"frankenstein_{tag}.jpg", quality=92)
    new_phone = "70" + "".join(random.choice(string.digits) for _ in range(8))
    reg["telecom"][new_phone] = {"activated": (date.today() - timedelta(days=3)).strftime("%d/%m/%Y"), "subscriber": victim["name"]}

    (GEN / "registry.json").write_text(json.dumps(reg))  # keep the enrolment across backend restarts

    url = lambda p: f"/files/demo/{p}"
    return {
        "genuine": {"card": url(f"genuine_{tag}.jpg"), "form": me},
        "hero_dob_edit": {"card": url(f"hero_dob_edit_{tag}.jpg"), "form": me | {"dob": "14/03/1994"},
                          "note": "Printed DOB was Poisson-blended to 1994; the signed QR still says 1998"},
        "frankenstein": {"card": url(f"frankenstein_{tag}.jpg"),
                         "form": {k: victim[k] for k in ("name", "dob", "gender", "id_number", "pan", "address", "pincode")}
                         | {"phone": new_phone, "email": f"fast.loans.{tag}@gmail.com"},
                         "note": "Real stolen ID number + your face; 3-day-old SIM"},
    }
