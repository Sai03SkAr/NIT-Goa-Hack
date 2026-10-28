"""Test kit: fresh identities (LFW faces never seen by the system), enrolled in the mock registries, with a card,
a selfie, form values, session signals and the EXPECTED decision for every scenario. Used by scripts/run_tests.py
and by people testing by hand in the browser (files land in data/generated/testkit/<tag>/).

Liveness fixtures: run_tests.py answers the server's real head-turn challenge with FIXTURE PHOTOS of the same person
(a frontal photo, a turned photo and its mirror image). The server verifies them exactly as it verifies a webcam
(one face, same person as the selfie, turn direction from facial landmarks), but they are not a live camera session."""
import json
import random
import string
import uuid
from datetime import date, timedelta

import cv2
import numpy as np
from PIL import Image

from app.config import DATA, GEN
from app.modules.biometric.face import embed, faces, reuse_threshold, sim, threshold
from app.modules.document import card as C
from app.modules.document.checksums import verhoeff_digit
from app.modules.document.qr_sign import forger_key, make_qr_text
from app.modules.registry import mocks

LFW = DATA / "lfw" / "lfw_home" / "lfw_funneled"
FIRST = {"M": ["Arjun", "Rohan", "Vikram", "Karthik", "Nikhil", "Siddharth", "Aditya", "Pranav", "Rahul", "Varun"],
         "F": ["Ananya", "Priya", "Kavya", "Sneha", "Meera", "Isha", "Divya", "Nisha", "Pooja", "Riya"]}
LAST = ["Naik", "Kamat", "Desai", "Prabhu", "Shetty", "Sawant", "Gaonkar", "Pai", "Rao", "Kulkarni", "Iyer", "Menon"]
STREETS = ["Miramar Road, Panaji", "MG Road, Margao", "18th June Road, Panaji", "Station Road, Vasco", "Market Road, Mapusa"]


def _fresh_people(n: int, hist, rng) -> list[list]:
    """LFW people with >=2 photos whose face is in neither the history nor the registry."""
    known = [np.stack(hist.faces)] if hist.faces else []
    reg = list(mocks._precomputed_faces().values()) + [e for e in mocks._face_cache.values() if e is not None]
    if reg:
        known.append(np.stack(reg))
    K = np.vstack(known) if known else np.zeros((0, 512), np.float32)
    dirs = [d for d in LFW.iterdir() if d.is_dir() and len(list(d.glob("*.jpg"))) >= 3]
    rng.shuffle(dirs)
    out, chosen = [], []
    for d in dirs:
        photos = sorted(d.glob("*.jpg"))[:6]
        embs = [e["emb"] for e in (embed(cv2.imread(str(p))) for p in photos[:2]) if e is not None]
        if len(embs) < 2:
            continue
        limit = 0.8 * reuse_threshold()
        # cheap "never seen" check first; the head-turn frame plan runs a dozen face detections
        if all((K @ e).max(initial=-1) < limit and all(float(e @ c) < limit for c in chosen) for e in embs) \
                and _frame_plan(photos) is not None:
            out.append(photos); chosen.extend(embs)
            if len(out) == n:
                return out
    raise RuntimeError("not enough unused LFW identities left for a test kit")


def _frame_plan(photos) -> dict | None:
    """Pick fixture frames: the most frontal photo as 'neutral' and a turned photo (plus its mirror) so both turn
    directions clear the server's landmark threshold with margin. None if this person has no usable turn."""
    selfie = embed(cv2.imread(str(photos[1])))
    if selfie is None:
        return None
    seen = []
    for p in photos:
        img = cv2.imread(str(p))
        for im, tag in ((img, "raw"), (cv2.flip(img, 1), "mirror")):
            f = faces(im)
            if len(f) == 1 and sim(f[0]["emb"], selfie["emb"]) >= threshold() + 0.05:
                seen.append({"path": p, "mirror": tag == "mirror", "r": f[0]["nose_ratio"]})
    raw = [x for x in seen if not x["mirror"]]
    if not raw:
        return None
    n = min(raw, key=lambda x: abs(x["r"] - 0.5))
    others = [x for x in seen if x["path"] != n["path"] and 0.10 <= abs(x["r"] - n["r"]) <= 0.35]
    left = [x for x in others if x["r"] - n["r"] > 0]
    right = [x for x in others if x["r"] - n["r"] < 0]
    if not left or not right:
        return None
    return {"neutral": n, "turn_left": max(left, key=lambda x: x["r"]), "turn_right": min(right, key=lambda x: x["r"])}


def _save_frames(photos, out_dir, sid, mode="live") -> dict:
    """mode live: neutral + both turns. still: the frontal photo re-saved (no head turn). replay: one still, copied."""
    plan = _frame_plan(photos)
    load = lambda x: cv2.flip(cv2.imread(str(x["path"])), 1) if x["mirror"] else cv2.imread(str(x["path"]))
    neutral = load(plan["neutral"])
    if mode == "live":
        imgs = {"neutral": neutral, "turn_left": load(plan["turn_left"]), "turn_right": load(plan["turn_right"])}
    elif mode == "still":  # a person who never turned: small lighting changes only
        imgs = {"neutral": neutral, "turn_left": cv2.convertScaleAbs(neutral, alpha=1.08, beta=6),
                "turn_right": cv2.convertScaleAbs(neutral, alpha=0.93, beta=-5)}
    else:  # replayed still image
        imgs = {k: neutral for k in ("neutral", "turn_left", "turn_right")}
    out = {}
    for k, im in imgs.items():
        f = out_dir / f"{sid}_frame_{k}.jpg"
        cv2.imwrite(str(f), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        out[k] = f"/files/{f.relative_to(GEN)}"
    return out


def _crop(path) -> Image.Image:
    return Image.open(path).convert("RGB").crop((25, 0, 225, 250))


def _payload(f):
    return {"n": f["name"].upper(), "d": f["dob"], "g": f["gender"], "id": f["id_number"], "i": f["issue_date"]}


def _fields(p):
    return {k: p[k] for k in ("name", "dob", "gender", "id_number", "issue_date")}


def build_testkit(hist, encrypted: int = 0) -> dict:
    """encrypted=N: instead of the scenario set, N genuine people whose card QR is signed AND encrypted (TID3)."""
    tag = uuid.uuid4().hex[:6]
    rng = random.Random(tag)
    out_dir = GEN / "testkit" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    reg = mocks.db()
    today = date.today()
    people = _fresh_people(encrypted or 21, hist, rng)
    pool = iter(people)

    def digits(n):
        return "".join(rng.choice(string.digits) for _ in range(n))

    def new_id():
        n11 = str(rng.randint(2, 9)) + digits(10)
        return n11 + verhoeff_digit(n11)

    def person(enrol=True, sim_days=None, surname=None):
        """An identity; enrol=True puts it in every registry with a long, clean history."""
        g = rng.choice("MF")
        name = f"{rng.choice(FIRST[g])} {surname or rng.choice(LAST)}"
        dob = today - timedelta(days=rng.randint(24, 55) * 365 + rng.randint(0, 300))
        issue = dob + timedelta(days=19 * 365 + rng.randint(0, 2000))
        p = {"name": name, "gender": g, "dob": dob.strftime("%d/%m/%Y"), "issue_date": issue.strftime("%d/%m/%Y"),
             "id_number": new_id(), "pan": "".join(rng.choice(string.ascii_uppercase) for _ in range(3)) + "P" + name.split()[-1][0] + digits(4) + rng.choice(string.ascii_uppercase),
             "phone": rng.choice("6789") + digits(9), "email": f"{name.split()[0].lower()}.{name.split()[-1].lower()}{digits(2)}@gmail.com",
             "address": f"{rng.randint(1, 300)}, {rng.choice(STREETS)}", "pincode": "403" + digits(3), "photos": next(pool)}
        if enrol:
            face = out_dir / f"registry_{p['id_number'][-4:]}.jpg"
            _crop(p["photos"][0]).save(face, quality=92)
            reg["uidai"][p["id_number"]] = {"name": name, "dob": p["dob"], "gender": g, "face": str(face.relative_to(GEN))}
            reg["pan"][p["pan"]] = {"name": name, "dob": p["dob"], "subject": p["id_number"]}
            reg["ckyc"][p["id_number"]] = {"first_seen": (today - timedelta(days=rng.randint(400, 3000))).strftime("%d/%m/%Y")}
            reg["bureau"][p["id_number"]] = {"accounts": rng.randint(2, 6), "oldest_months": rng.randint(60, 180), "inquiries_90d": rng.randint(0, 1)}
            mocks._face_cache.pop(p["id_number"], None)
        reg["telecom"][p["phone"]] = {"activated": (today - timedelta(days=sim_days or rng.randint(900, 4000))).strftime("%d/%m/%Y"),
                                      "subscriber": name}
        return p

    def new_sim(name):
        ph = rng.choice("6789") + digits(9)
        reg["telecom"][ph] = {"activated": (today - timedelta(days=3)).strftime("%d/%m/%Y"), "subscriber": name}
        return ph

    def form(p, **over):
        return {k: p[k] for k in ("name", "dob", "gender", "id_number", "pan", "phone", "email", "address", "pincode")} | over

    scenarios = []

    def _finish():
        (GEN / "registry.json").write_text(json.dumps(reg))  # survive backend restarts
        kit = {"tag": tag, "folder": str(out_dir), "scenarios": scenarios}
        (out_dir / "kit.json").write_text(json.dumps(kit, indent=1))
        (out_dir / "MANUAL.md").write_text(manual_sheet(kit))
        return kit

    def add(sid, title, expect, why, p_form, card_img, selfie_path, signals="human", live="live", camera="FaceTime HD Camera",
            device=None, manual=True, frames_of=None):
        """live: 'live' (fixture frames that really turn), 'still' (no head turn), 'replay' (one still copied)."""
        card_file, selfie_file = out_dir / f"{sid}_card.jpg", out_dir / f"{sid}_selfie.jpg"
        card_img.save(card_file, quality=90)
        Image.open(selfie_path).convert("RGB").save(selfie_file, quality=92)
        frames = _save_frames(frames_of, out_dir, sid, live)
        scenarios.append({"id": sid, "title": title, "expect": expect, "why": why, "form": p_form,
                          "card": f"/files/{card_file.relative_to(GEN)}", "selfie": f"/files/{selfie_file.relative_to(GEN)}",
                          "signals": signals, "liveness": live, "frames": frames, "camera": camera,
                          "device_id": device or f"Dtest{tag}{len(scenarios):02d}", "manual": manual})

    def genuine_card(p):
        return C.render(_fields(p), _crop(p["photos"][0]), make_qr_text(_payload(_fields(p))))

    if encrypted:
        for k in range(encrypted):
            p = person()
            card = C.render(_fields(p), _crop(p["photos"][0]), make_qr_text(_payload(_fields(p)), encrypt=True))
            add(f"enc_{k + 1:02d}", f"Genuine applicant {k + 1}, encrypted QR", ["REVIEW"],
                "Registry citizen with a card whose QR is signed and AES-encrypted: a phone scan shows only ciphertext; "
                "the server decrypts it, verifies the signature and compares it with the card and form. REVIEW because "
                "scripted still photos can't pass the live head-turn; on a webcam this is APPROVE.",
                form(p), card, p["photos"][1], frames_of=p["photos"])
        return _finish()

    # --- should be APPROVED
    p = person()
    add("01_genuine", "Genuine applicant (scripted still photos)", ["REVIEW"],
        "Real registry citizen, everything matches. Scripted frames are still photos, so the live head-turn cannot be "
        "confirmed (REVIEW). The same person on a real webcam is APPROVE.",
        form(p), genuine_card(p), p["photos"][1], frames_of=p["photos"])
    p = person()
    initial = f"{p['name'].split()[0][0]}. {p['name'].split()[-1]}"
    add("02_name_initial", "Genuine, name written with an initial", ["REVIEW"],
        f"Form says '{initial}' but the card says '{p['name']}'; Indian-name fuzzy matching accepts it. REVIEW only "
        "because scripted still photos can't prove a live head-turn.",
        form(p, name=initial), genuine_card(p), p["photos"][1], frames_of=p["photos"])

    # --- should be REVIEWED (genuine person, but a check could not complete)
    p = person()
    add("03_liveness_failed", "Genuine, but the head-turn challenge was not performed", ["REVIEW", "REJECT"],
        "Everything matches, but the person never turned their head: the server sees no turn and fails liveness. "
        "A failed liveness check can never be approved automatically.",
        form(p), genuine_card(p), p["photos"][1], live="still", frames_of=p["photos"])

    # --- should be REJECTED
    p = person()
    edited_dob = (date(*reversed([int(x) for x in p["dob"].split("/")])) - timedelta(days=4 * 365)).strftime("%d/%m/%Y")
    add("04_dob_edit", "Hero attack: date of birth edited on the card", ["REJECT"],
        f"Printed DOB was seamlessly changed to {edited_dob}; the issuer-signed QR still holds {p['dob']}.",
        form(p, dob=edited_dob), C.poisson_edit(genuine_card(p), "dob", edited_dob), p["photos"][1], frames_of=p["photos"])
    p = person()
    add("05_forged_qr", "Counterfeit card (QR signed with a fake key)", ["REJECT"],
        "Card re-printed by a forger: the QR looks valid but its signature fails against the issuer's public key.",
        form(p), C.render(_fields(p), _crop(p["photos"][0]), make_qr_text(_payload(_fields(p)), forger_key())), p["photos"][1],
        frames_of=p["photos"])
    victim, thief = person(), person(enrol=False)
    frank = C.splice_portrait(genuine_card(victim), _crop(thief["photos"][0]))
    add("06_frankenstein", "Stolen identity (real ID number + someone else's face)", ["REJECT"],
        "Victim's genuine card with the fraudster's photo pasted in; selfie matches the card but NOT the registry photo; 3-day-old SIM.",
        form(victim, phone=new_sim(victim["name"])), frank, thief["photos"][1], frames_of=thief["photos"])
    fab = person(enrol=False)
    add("07_fabricated", "Fabricated identity (ID number not issued, no QR)", ["REJECT", "REVIEW"],
        "Checksum-valid but never-issued ID number, card without a signed QR, no credit or KYC history, new SIM.",
        form(fab, phone=new_sim(fab["name"])), C.render(_fields(fab), _crop(fab["photos"][0]), None), fab["photos"][1],
        frames_of=fab["photos"])
    p, other = person(), person(enrol=False)
    add("08_selfie_mismatch", "Someone else's face at the camera", ["REJECT", "REVIEW"],
        "Genuine card and details, but the person doing the selfie is not the card holder.",
        form(p), genuine_card(p), other["photos"][1], frames_of=other["photos"])
    p = person()
    bad_id = p["id_number"][:-1] + str((int(p["id_number"][-1]) + 3) % 10)
    add("09_id_typo", "ID number with a wrong digit", ["REJECT", "REVIEW"],
        "Last digit changed: fails the Verhoeff checksum and disagrees with the card.",
        form(p, id_number=bad_id), genuine_card(p), p["photos"][1], frames_of=p["photos"])
    p = person()
    add("10_virtual_camera", "Deepfake injection through a virtual camera", ["REVIEW", "REJECT"],
        "The browser reports 'OBS Virtual Camera' as the active camera, a common way to inject deepfake video. "
        "Camera names are client-reported hints (an attacker can rename a device), so this blocks automatic "
        "approval rather than proving fraud.",
        form(p), genuine_card(p), p["photos"][1], camera="OBS Virtual Camera", manual=False, frames_of=p["photos"])
    p = person()
    add("11_bot", "Scripted bot submission", ["REJECT", "REVIEW"],
        "All fields pasted in 7 seconds with machine-regular key timing; the same still image was replayed as every liveness frame.",
        form(p), genuine_card(p), p["photos"][0], signals="bot", live="replay", manual=False, frames_of=p["photos"])
    boss = person(enrol=False)
    ring_dev = f"Dring{tag}"
    for k in range(3):
        v = person()
        card = C.splice_portrait(genuine_card(v), _crop(boss["photos"][0]))
        add(f"12_ring_{k + 1}", f"Fraud ring member {k + 1} of 3", ["REJECT"],
            "Different stolen identities, but one face, one device, one typing rhythm and emails ring.sv01/02/03.",
            form(v, email=f"ring.sv{tag}{k + 1:02d}@gmail.com", phone=new_sim(v["name"])), card, boss["photos"][1],
            signals="ring", device=ring_dev, manual=False, frames_of=boss["photos"])

    # mule herding: three REAL, fully genuine people (own card, own face, own registry record) onboarded one after
    # another from the same phone. Each looks clean alone; the third reveals the recruiter's device.
    mule_dev = f"Dmule{tag}"
    for k, sur in enumerate(rng.sample(LAST, 3)):
        m = person(surname=sur)
        add(f"13_mule_{k + 1}", f"Recruited account holder {k + 1} of 3 (same phone)", ["REVIEW"],
            "Genuine person and documents, but the same device has onboarded other unrelated people. The third member "
            "trips the mule-herding pattern (COR_MULE_HERDING). All three are REVIEW here because scripted stills "
            "can't pass the live check; on a webcam members 1 and 2 would be APPROVE.",
            form(m), genuine_card(m), m["photos"][1], device=mule_dev, manual=False, frames_of=m["photos"])

    return _finish()


def manual_sheet(kit: dict) -> str:
    """Browser test sheet. An uploaded selfie skips live liveness, so a clean applicant lands in REVIEW, not APPROVE."""
    L = [f"# Manual test sheet — kit {kit['tag']}", "",
         "Open http://localhost:3001/kyc (or :3000). For each scenario: tick consent, **type** the form values,",
         "upload the card file at step 3, and at step 4 click **'No camera? Upload a selfie'** and pick the selfie file.",
         "Each identity is single-use: submit each scenario once (re-using an identity triggers velocity signals).", ""]
    for s in kit["scenarios"]:
        if not s["manual"]:
            continue
        exp = " or ".join(s["expect"]) + " (an uploaded selfie or scripted stills cannot pass the live head-turn; only a real webcam reaches APPROVE)"
        f = s["form"]
        L += [f"## {s['id']} — {s['title']}", f"**Expected:** {exp}  ", f"**Why:** {s['why']}", "",
              f"- Card file: `{s['id']}_card.jpg`  ·  Selfie file: `{s['id']}_selfie.jpg`",
              f"- Name `{f['name']}` · DOB `{f['dob']}` · Gender `{'Male' if f['gender'] == 'M' else 'Female'}`",
              f"- National ID `{f['id_number']}` · PAN `{f['pan']}` · Mobile `{f['phone']}`",
              f"- Email `{f['email']}` · Address `{f['address']}` · PIN `{f['pincode']}`", ""]
    return "\n".join(L)
