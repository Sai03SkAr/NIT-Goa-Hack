"""Synthetic KYC population (plan section 5).

Classes: genuine, hard_negative (family / hostel / transliteration / new-to-credit / repeat), first_party,
third_party, ring, bot, tampered. Writes data/generated/{population.json, registry.json, cards/, selfies/, faces/}.

Leakage controls: every card in every class gets random resize + noise + JPEG quality 60-95.
Run:  python data/gen_population.py --n 1400
"""
import argparse
import io
import json
import random
import string
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from faker import Faker
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import DATA, GEN  # noqa: E402
from app.modules.document import card as C  # noqa: E402
from app.modules.document.checksums import verhoeff_digit  # noqa: E402
from app.modules.document.qr_sign import forger_key, make_qr_text  # noqa: E402

START = datetime(2026, 9, 1, 0, 0, 0)
TODAY = date(2026, 10, 1)
SHARES = {"genuine": 0.70, "hard_negative": 0.10, "first_party": 0.04, "third_party": 0.04,
          "ring": 0.06, "bot": 0.03, "tampered": 0.03}
UAS = ["Mozilla/5.0 (Linux; Android 14; SM-A546E) Chrome/129", "Mozilla/5.0 (Linux; Android 13; Redmi Note 12) Chrome/128",
       "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5) Safari/604.1", "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/129",
       "Mozilla/5.0 (Linux; Android 12; vivo 1938) Chrome/127", "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/605"]
REAL_CAMS = ["Integrated Webcam", "FaceTime HD Camera", "Front Camera", "USB2.0 HD UVC WebCam"]
VIRTUAL_CAMS = ["OBS Virtual Camera", "ManyCam Virtual Webcam", "XSplit VCam"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.co.in", "outlook.com", "rediffmail.com"]

rng = np.random.default_rng(7)
random.seed(7)
fake = Faker("en_IN")
Faker.seed(7)


# ---------------------------------------------------------------- faces
def load_lfw():
    """People with >= 2 photos, as lists of file paths (lazy: never holds all 9k images in memory)."""
    import tarfile
    home = DATA / "lfw" / "lfw_home"
    root = home / "lfw_funneled"
    if not root.exists():
        with tarfile.open(home / "lfw-funneled.tgz") as t:
            t.extractall(home, filter="data")
    people = [sorted(d.glob("*.jpg")) for d in sorted(root.iterdir()) if d.is_dir()]
    people = [p for p in people if len(p) >= 2]
    random.shuffle(people)
    return people


class Faces:
    def __init__(self):
        self.people = load_lfw()
        self.next = 0

    def take_person(self) -> list[Image.Image]:
        if self.next >= len(self.people):
            raise SystemExit("Ran out of LFW identities; lower --n")
        paths = self.people[self.next]
        self.next += 1
        return [Image.open(p).convert("RGB") for p in paths[:4]]


def portrait_crop(img: Image.Image) -> Image.Image:
    return img.crop((25, 0, 225, 250))


# ---------------------------------------------------------------- identity helpers
def new_id_number(used: set) -> str:
    while True:
        n11 = str(random.randint(2, 9)) + "".join(random.choice(string.digits) for _ in range(10))
        n = n11 + verhoeff_digit(n11)
        if n not in used:
            used.add(n)
            return n


def new_pan(surname: str, used: set) -> str:
    while True:
        p = "".join(random.choice(string.ascii_uppercase) for _ in range(3)) + "P" + surname[0].upper() + \
            f"{random.randint(0, 9999):04d}" + random.choice(string.ascii_uppercase)
        if p not in used:
            used.add(p)
            return p


def new_phone(used: set) -> str:
    while True:
        p = str(random.choice([6, 7, 8, 9])) + "".join(random.choice(string.digits) for _ in range(9))
        if p not in used:
            used.add(p)
            return p


def person_name(gender: str, surname: str | None = None) -> str:
    first = fake.first_name_male() if gender == "M" else fake.first_name_female()
    return f"{first} {surname or fake.last_name()}"


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def rand_dob(age_lo: int, age_hi: int) -> date:
    return TODAY - timedelta(days=int(rng.uniform(age_lo, age_hi) * 365.25))


def issue_after(dob: date) -> date:
    lo = dob + timedelta(days=int(18 * 365.25))
    hi = TODAY - timedelta(days=60)
    lo = min(lo, hi - timedelta(days=30))
    return lo + timedelta(days=int(rng.uniform(0, (hi - lo).days)))


def email_for(name: str, used: set, stem: str | None = None, seq: int | None = None) -> str:
    if stem is not None:
        e = f"{stem}{seq:02d}@{random.choice(EMAIL_DOMAINS)}"
    else:
        f, l = name.lower().split()[0], name.lower().split()[-1]
        style = random.random()
        base = f"{f}.{l}" if style < .5 else (f"{f}{l[0]}" if style < .8 else f"{f}_{l}")
        e = base + (str(random.randint(1, 999)) if random.random() < .6 else "") + "@" + random.choice(EMAIL_DOMAINS)
    while e in used:
        e = e.replace("@", str(random.randint(0, 9)) + "@", 1)
    used.add(e)
    return e


def address() -> tuple[str, str]:
    return f"{fake.building_number()}, {fake.street_name()}, {fake.city()}", fake.postcode()


def translit_variant(name: str) -> str:
    first, last = name.split()[0], name.split()[-1]
    r = random.random()
    if r < .4:
        return f"{first[0]}. {last}"
    swaps = [("ee", "i"), ("oo", "u"), ("sh", "s"), ("v", "w"), ("aa", "a")]
    for a, b in random.sample(swaps, len(swaps)):
        if a in first.lower():
            return f"{first.lower().replace(a, b, 1).title()} {last}"
    return f"{first}a {last}" if not first.endswith("a") else f"{first[:-1]} {last}"


def typo(name: str) -> str:
    i = random.randint(1, max(1, len(name) - 2))
    return name[:i] + name[i + 1] + name[i] + name[i + 2:] if name[i] != " " and name[i + 1] != " " else name


# ---------------------------------------------------------------- telemetry
def keystroke_profile() -> np.ndarray:
    return rng.normal(0, 1, 12)


def telemetry(kind: str, profile: np.ndarray, practiced=False) -> dict:
    if kind == "bot":
        humanized = random.random() < .35
        fill = rng.uniform(25, 50) if humanized else rng.uniform(5, 14)
        iki_m = rng.normal(95, 15) if humanized else rng.normal(38, 5)
        iki_s = rng.normal(40, 10) if humanized else abs(rng.normal(3, 1))
        paste = random.randint(3, 5) if humanized else random.randint(5, 7)
        corr, blur, ment = 0, 0, abs(rng.normal(.8, .3))
        vec = rng.normal(0, .05, 12) + (2.5 if not humanized else 0)
    else:
        slow = kind == "slow"
        power = not practiced and random.random() < .10   # genuine power users: autofill / paste from notes
        fill = rng.lognormal(np.log(62 if practiced else (140 if slow else (35 if power else 85))), .4)
        iki_m = rng.normal(165 if practiced else (260 if slow else 185), 35)
        iki_s = rng.normal(65, 20)
        paste = int(rng.binomial(7, .05)) + (1 if random.random() < .3 else 0)
        if practiced:
            paste += random.randint(0, 2)
        if power:
            paste += random.randint(2, 5)
        corr = int(rng.poisson(3)); blur = int(rng.poisson(.7 if not practiced else 2)); ment = rng.normal(3.5, .5)
        vec = profile + rng.normal(0, .25, 12)
    ft = rng.dirichlet(np.ones(7)) * fill
    return {"field_times": [round(float(x), 2) for x in ft], "fill_time": round(float(fill), 1),
            "iki_mean": round(float(max(iki_m, 5)), 1), "iki_std": round(float(max(iki_s, .5)), 1),
            "paste_fields": int(min(paste, 7)), "corrections": corr, "blur_count": blur,
            "mouse_entropy": round(float(max(ment, 0)), 2), "keystroke_vec": [round(float(v), 3) for v in vec]}


# ---------------------------------------------------------------- images
def degrade(img: Image.Image, out: Path, moire=False):
    """Leakage control: same random resize/noise/JPEG for every class."""
    s = rng.uniform(.8, 1.2)
    img = img.resize((int(img.width * s), int(img.height * s)), Image.BILINEAR)
    a = np.asarray(img).astype(np.float32)
    if moire:
        yy, xx = np.mgrid[:a.shape[0], :a.shape[1]]
        a += 14 * np.sin(xx * .9 + yy * .35)[..., None]
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.6))
        a = np.asarray(img).astype(np.float32)
    a += rng.normal(0, rng.uniform(0, 4), a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    q = int(rng.integers(60, 96))
    img.save(out, "JPEG", quality=q)
    return {"jpeg_q": q, "scale": round(float(s), 3)}


def make_card(fields: dict, portrait: Image.Image, qr: str | None) -> Image.Image:
    return C.render(fields, portrait_crop(portrait), qr)


def card_fields(p: dict) -> dict:
    return {"name": p["name"], "dob": p["dob"], "gender": p["gender"], "id_number": p["id_number"],
            "issue_date": p["issue_date"]}


def qr_payload(f: dict) -> dict:
    return {"n": f["name"].upper(), "d": f["dob"], "g": f["gender"], "id": f["id_number"], "i": f["issue_date"]}


# ---------------------------------------------------------------- main generation
def main(n: int):
    faces = Faces()
    used_ids, used_pans, used_phones, used_emails = set(), set(), set(), set()
    reg = {"uidai": {}, "pan": {}, "telecom": {}, "ckyc": {}, "bureau": {}}
    apps = []
    (GEN / "cards").mkdir(exist_ok=True)
    (GEN / "selfies").mkdir(exist_ok=True)
    (GEN / "registry_faces").mkdir(exist_ok=True)
    cgnat = [f"49.36.{random.randint(0, 255)}.{random.randint(1, 254)}" for _ in range(220)]

    def citizen(gender=None, surname=None, age=(22, 68), sim_days=None, thin=False, ckyc=True, phone=None,
                addr=None, sim_name=None):
        g = gender or random.choice("MF")
        name = person_name(g, surname)
        dob = rand_dob(*age)
        imgs = faces.take_person()
        cid = f"C{len(reg['uidai']):05d}"
        idn = new_id_number(used_ids)
        surname_ = name.split()[-1]
        p = {"cid": cid, "name": name, "gender": g, "dob": dmy(dob), "id_number": idn,
             "issue_date": dmy(issue_after(dob)), "pan": new_pan(surname_, used_pans),
             "phone": phone or new_phone(used_phones), "imgs": imgs}
        p["address"], p["pincode"] = addr or address()
        reg_face = GEN / "registry_faces" / f"{cid}.jpg"
        portrait_crop(imgs[0]).save(reg_face, quality=92)
        reg["uidai"][idn] = {"name": name, "dob": p["dob"], "gender": g, "face": str(reg_face.relative_to(GEN))}
        reg["pan"][p["pan"]] = {"name": name, "dob": p["dob"], "subject": idn}
        if p["phone"] not in reg["telecom"]:
            sd = sim_days if sim_days is not None else int(rng.uniform(400, 4000))
            reg["telecom"][p["phone"]] = {"activated": dmy(TODAY - timedelta(days=sd)), "subscriber": sim_name or name}
        age_y = (TODAY - dob).days / 365.25
        if ckyc:
            reg["ckyc"][idn] = {"first_seen": dmy(TODAY - timedelta(days=int(rng.uniform(200, 3000))))}
        if not thin:
            reg["bureau"][idn] = {"accounts": int(1 + rng.poisson(max(age_y - 18, 1) / 8)),
                                  "oldest_months": int(rng.uniform(12, max(13, (age_y - 18) * 12))),
                                  "inquiries_90d": int(rng.poisson(.8))}
        p["profile"] = keystroke_profile()
        return p

    def fraud_person():
        imgs = faces.take_person()
        return {"imgs": imgs, "profile": keystroke_profile()}

    def ts_on(day: float) -> datetime:
        hour = rng.normal(14, 4) % 24
        return START + timedelta(days=int(day), hours=float(hour), minutes=float(rng.uniform(0, 60)))

    def emit(kind, label, p_form, card_img, selfie_img, tele, device, ts, liveness, group=None, meta=None,
             selfie_replay=False, target=None, prefix="A"):
        target = apps if target is None else target
        app_id = f"{prefix}{len(target):05d}"
        cmeta = degrade(card_img, GEN / "cards" / f"{app_id}.jpg")
        degrade(selfie_img.convert("RGB"), GEN / "selfies" / f"{app_id}.jpg", moire=selfie_replay)
        target.append({"app_id": app_id, "ts": ts.isoformat(), "day": (ts - START).days, "label": int(label),
                     "fraud_type": kind, "group": group, "meta": {**(meta or {}), **cmeta},
                     "form": p_form, "device": device, "telemetry": tele, "liveness": liveness,
                     "card_path": f"cards/{app_id}.jpg", "selfie_path": f"selfies/{app_id}.jpg"})

    def form_of(p, **over):
        f = {k: p[k] for k in ("name", "dob", "gender", "id_number", "pan", "phone", "address", "pincode")}
        f["email"] = over.pop("email", None) or email_for(p["name"], used_emails)
        f.update(over)
        return f

    def device(dev_id=None, ip=None, virtual=False):
        installed = virtual or random.random() < .04  # streamers have OBS installed but use the real camera
        cams = [random.choice(REAL_CAMS)] + ([random.choice(VIRTUAL_CAMS)] if installed else [])
        return {"device_id": dev_id or f"D{random.getrandbits(40):010x}", "ip": ip or random.choice(cgnat),
                "user_agent": random.choice(UAS), "camera_labels": cams,
                "active_camera": cams[-1] if virtual else cams[0]}

    def live(passed=True, consistent=True, virtual=False, replay=False):
        ch = random.sample(["blink", "turn_left", "turn_right", "smile"], 2)
        return {"challenges": ch, "passed": bool(passed), "frames_consistent": bool(consistent),
                "virtual_camera": bool(virtual), "replay_suspected": bool(replay)}

    def genuine_card(p):
        f = card_fields(p)
        return make_card(f, p["imgs"][0], make_qr_text(qr_payload(f)))

    counts = {k: int(round(v * n)) for k, v in SHARES.items()}
    counts["genuine"] = n - sum(v for k, v in counts.items() if k != "genuine")
    spare = []  # registry citizens who never apply: stolen-identity pool

    # ---- genuine
    for _ in range(counts["genuine"]):
        p = citizen(thin=random.random() < .12, ckyc=random.random() < .88)
        nm = typo(p["name"]) if random.random() < .03 else p["name"]
        emit("genuine", 0, form_of(p, name=nm), genuine_card(p), p["imgs"][-1], telemetry("human", p["profile"]),
             device(), ts_on(rng.uniform(0, 30)), live(passed=random.random() > .04))

    # ---- hard negatives
    hn_left = counts["hard_negative"]
    while hn_left > 0:
        sub = random.choice(["family", "family", "hostel", "translit", "newcredit", "repeat"])
        if sub == "family":
            k = min(hn_left, random.randint(2, 4))
            surname, addr = fake.last_name(), address()
            head = citizen(surname=surname, addr=addr, age=(40, 65))
            shared_dev = f"D{random.getrandbits(40):010x}" if random.random() < .5 else None
            day = rng.uniform(0, 26)
            members = [head] + [citizen(surname=surname, addr=addr, phone=head["phone"], age=(19, 70))
                                for _ in range(k - 1)]
            for m in members:
                emit("hard_negative", 0, form_of(m), genuine_card(m), m["imgs"][-1], telemetry("slow" if random.random() < .3 else "human", m["profile"]),
                     device(shared_dev), ts_on(day + rng.uniform(0, 4)), live(), group=f"family:{surname}", meta={"sub": "family"})
            hn_left -= k
        elif sub == "hostel":
            k = min(hn_left, random.randint(5, 10))
            ip, day = f"14.139.{random.randint(0, 255)}.{random.randint(1, 254)}", rng.uniform(0, 26)
            for _ in range(k):
                s = citizen(age=(18.2, 22), sim_days=int(rng.uniform(3, 60)), thin=True, ckyc=random.random() < .3)
                emit("hard_negative", 0, form_of(s), genuine_card(s), s["imgs"][-1], telemetry("human", s["profile"]),
                     device(ip=ip), ts_on(day + rng.uniform(0, 3)), live(), group=f"hostel:{ip}", meta={"sub": "hostel"})
            hn_left -= k
        elif sub == "translit":
            p = citizen()
            emit("hard_negative", 0, form_of(p, name=translit_variant(p["name"])), genuine_card(p), p["imgs"][-1],
                 telemetry("human", p["profile"]), device(), ts_on(rng.uniform(0, 30)), live(), meta={"sub": "translit"})
            hn_left -= 1
        elif sub == "newcredit":
            p = citizen(age=(25, 55), thin=True, ckyc=False, sim_days=int(rng.uniform(10, 200)))
            emit("hard_negative", 0, form_of(p), genuine_card(p), p["imgs"][-1], telemetry("slow", p["profile"]),
                 device(), ts_on(rng.uniform(0, 30)), live(), meta={"sub": "newcredit"})
            hn_left -= 1
        else:  # same person applies twice for two products: face reuse with the SAME name is fine
            p = citizen()
            day = rng.uniform(0, 25)
            for j in range(2):
                emit("hard_negative", 0, form_of(p, email=None) if j == 0 else form_of(p), genuine_card(p), p["imgs"][-1 - j % len(p["imgs"])],
                     telemetry("human", p["profile"]), device(), ts_on(day + j * rng.uniform(1, 4)), live(), meta={"sub": "repeat"})
            hn_left -= 2

    # stolen-identity pool: real registry citizens who never apply themselves
    n_stolen = counts["first_party"] + counts["bot"] + counts["tampered"] + counts["ring"]
    spare = [citizen(thin=random.random() < .1) for _ in range(n_stolen)]

    def fraud_sim(name, days=(1, 25)):
        ph = new_phone(used_phones)
        reg["telecom"][ph] = {"activated": dmy(TODAY - timedelta(days=int(rng.uniform(*days)))), "subscriber": name}
        return ph

    # ---- first-party / Frankenstein
    for _ in range(counts["first_party"]):
        v, fr = spare.pop(), fraud_person()
        fname = person_name(random.choice("MF"))
        if random.random() < .6:   # stolen ID: copied genuine QR, spliced portrait
            f = card_fields(v)
            card = C.splice_portrait(make_card(f, v["imgs"][0], make_qr_text(qr_payload(f))), portrait_crop(fr["imgs"][0]))
            ph = v["phone"] if random.random() < .3 else fraud_sim(random.choice([fname, v["name"]]))  # 30%: SIM swap
            form = form_of(v, phone=ph, address=address()[0])
            sub = "stolen_id"
        else:                       # Frankenstein: real number + invented name/DOB, QR signed by a forger
            f = {**card_fields(v), "name": fname, "dob": dmy(rand_dob(25, 50))}
            card = make_card(f, fr["imgs"][0], make_qr_text(qr_payload(f), forger_key()))
            form = form_of(v, name=fname, dob=f["dob"], phone=fraud_sim(fname))
            sub = "frankenstein"
        emit("first_party", 1, form, card, fr["imgs"][-1], telemetry("human", fr["profile"], practiced=True),
             device(virtual=random.random() < .1), ts_on(rng.uniform(0, 30)), live(), meta={"sub": sub})

    # ---- third-party fabricated
    for _ in range(counts["third_party"]):
        fr, g = fraud_person(), random.choice("MF")
        name = person_name(g)
        dob = rand_dob(24, 45)
        p = {"name": name, "gender": g, "dob": dmy(dob), "id_number": new_id_number(used_ids),
             "issue_date": dmy(issue_after(dob)), "pan": new_pan(name.split()[-1], used_pans)}
        p["phone"] = fraud_sim(name, (2, 40))
        p["address"], p["pincode"] = address()
        if random.random() < .4:  # "seasoned" synthetic: built a small credit file before the bust-out
            reg["bureau"][p["id_number"]] = {"accounts": random.randint(2, 3), "oldest_months": random.randint(6, 12),
                                             "inquiries_90d": random.randint(4, 9)}
        qr = make_qr_text(qr_payload(card_fields(p)), forger_key()) if random.random() < .7 else None
        vc = random.random() < .15
        emit("third_party", 1, form_of(p), make_card(card_fields(p), fr["imgs"][0], qr), fr["imgs"][-1],
             telemetry("human", fr["profile"], practiced=True), device(virtual=vc), ts_on(rng.uniform(0, 30)),
             live(virtual=vc), meta={"sub": "fabricated"})

    # ---- rings
    ring_left, r = counts["ring"], 0
    while ring_left > 0:
        k = min(ring_left, random.randint(5, 10))
        slow = random.random() < .3   # slow-and-low: spread out, distinct devices/IPs
        boss = [fraud_person() for _ in range(random.choice([1, 1, 2]))]
        stem = fake.user_name().replace(".", "")[:8] + "."
        devs = [f"D{random.getrandbits(40):010x}" for _ in range(2)]
        ips = [random.choice(cgnat) for _ in range(2)]
        addrs = [address() for _ in range(2)]
        day0 = rng.uniform(0, 22 if not slow else 8)
        for j in range(k):
            fr = boss[j % len(boss)]
            if spare and random.random() < .5:
                v = spare.pop()
                f = card_fields(v)
                card = C.splice_portrait(make_card(f, v["imgs"][0], make_qr_text(qr_payload(f))), portrait_crop(fr["imgs"][0]))
                pf = form_of(v, email=email_for("", used_emails, stem, j + 1), phone=fraud_sim(v["name"]))
            else:
                g = random.choice("MF")
                name = person_name(g)
                dob = rand_dob(23, 45)
                pf = {"name": name, "gender": g, "dob": dmy(dob), "id_number": new_id_number(used_ids),
                      "issue_date": dmy(issue_after(dob)), "pan": new_pan(name.split()[-1], used_pans)}
                card = make_card(card_fields(pf), fr["imgs"][0], make_qr_text(qr_payload(card_fields(pf)), forger_key()))
                pf = {k_: pf[k_] for k_ in ("name", "dob", "gender", "id_number", "pan")}
                pf["phone"] = fraud_sim(name)
                pf["email"] = email_for("", used_emails, stem, j + 1)
            if not slow:
                pf["address"], pf["pincode"] = random.choice(addrs)
                dv = device(random.choice(devs), random.choice(ips), virtual=random.random() < .15)
                when = ts_on(day0 + rng.uniform(0, 5))
            else:
                pf["address"], pf["pincode"] = address()
                dv = device()
                when = ts_on(day0 + rng.uniform(0, 21))
            if random.random() < .3 and j > 0:
                pf["phone"] = apps[-1]["form"]["phone"]  # reuse a ring phone
            emit("ring", 1, pf, card, fr["imgs"][-1 - (j % max(1, len(fr["imgs"]) - 1))],
                 telemetry("human", fr["profile"], practiced=True), dv, when, live(virtual=dv["active_camera"] in VIRTUAL_CAMS),
                 group=f"ring:{r}", meta={"sub": "slow" if slow else "fast"})
        ring_left -= k
        r += 1

    # ---- bots: scripted bursts with stolen real identities + replayed photos
    bot_left = counts["bot"]
    while bot_left > 0:
        k = min(bot_left, random.randint(3, 8))
        dv_id, ip, day = f"D{random.getrandbits(40):010x}", random.choice(cgnat), rng.uniform(0, 29)
        base = START + timedelta(days=int(day), hours=float(rng.uniform(0, 23)))
        for j in range(k):
            v = spare.pop() if spare else citizen()
            vc = random.random() < .3
            replay = not vc
            emit("bot", 1, form_of(v), genuine_card(v), v["imgs"][0], telemetry("bot", None),
                 device(dv_id, ip, virtual=vc), base + timedelta(minutes=float(j * rng.uniform(1, 9))),
                 live(passed=random.random() < .25, consistent=False, virtual=vc, replay=replay),
                 group=f"bot:{dv_id}", selfie_replay=replay)
        bot_left -= k

    # ---- tampered documents
    for _ in range(counts["tampered"]):
        v = spare.pop() if spare else citizen()
        f = card_fields(v)
        card = make_card(f, v["imgs"][0], make_qr_text(qr_payload(f)))
        if random.random() < .65:   # Poisson-blended DOB edit (DeepID hero attack)
            new_dob = dmy(datetime.strptime(v["dob"], "%d/%m/%Y").date() - timedelta(days=int(rng.uniform(400, 2500))))
            card = C.poisson_edit(card, "dob", new_dob)
            emit("tampered", 1, form_of(v, dob=new_dob), card, v["imgs"][-1], telemetry("human", v["profile"]),
                 device(), ts_on(rng.uniform(0, 30)), live(), meta={"sub": "dob_edit"})
        else:                       # name edit + face splice
            fr = fraud_person()
            nm = person_name(v["gender"])
            card = C.splice_portrait(C.poisson_edit(card, "name", nm.upper()), portrait_crop(fr["imgs"][0]))
            emit("tampered", 1, form_of(v, name=nm, phone=fraud_sim(nm)), card, fr["imgs"][-1],
                 telemetry("human", fr["profile"], practiced=True), device(), ts_on(rng.uniform(0, 30)), live(),
                 meta={"sub": "name_face_edit"})

    # ---- ring-simulator kit (injected live from the analyst console; never in training data)
    kit, boss = [], fraud_person()
    stem, dev, ip = "quickloans.", f"D{random.getrandbits(40):010x}", random.choice(cgnat)
    shared_addr = address()
    for j in range(8):
        v = citizen(thin=True, ckyc=False)
        f = card_fields(v)
        card = C.splice_portrait(make_card(f, v["imgs"][0], make_qr_text(qr_payload(f))), portrait_crop(boss["imgs"][0]))
        pf = form_of(v, email=email_for("", used_emails, stem, j + 1), phone=fraud_sim(v["name"]),
                     address=shared_addr[0], pincode=shared_addr[1])
        emit("ring", 1, pf, card, boss["imgs"][-1 - (j % max(1, len(boss["imgs"]) - 1))],
             telemetry("human", boss["profile"], practiced=True), device(dev, ip), START, live(),
             group="ring:sim", target=kit, prefix="RS")
    (GEN / "ring_sim.json").write_text(json.dumps(kit, indent=0))

    # ---- spare stolen identities for the live demo kit (/api/demo/kit)
    demo_spares = []
    for _ in range(3):
        v = citizen()
        demo_spares.append({k: v[k] for k in ("name", "dob", "gender", "id_number", "issue_date", "pan", "phone",
                                                "address", "pincode")} | {"face": f"registry_faces/{v['cid']}.jpg"})
    (GEN / "demo_spares.json").write_text(json.dumps(demo_spares, indent=1))

    apps.sort(key=lambda a: a["ts"])
    (GEN / "population.json").write_text(json.dumps(apps, indent=0))
    (GEN / "registry.json").write_text(json.dumps(reg))
    from collections import Counter
    print("apps:", len(apps), Counter(a["fraud_type"] for a in apps))
    print("registry ids:", len(reg["uidai"]), "faces used:", faces.next, "of", len(faces.people))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1400)
    main(ap.parse_args().n)
