"""Simulated digital-footprint source for the synthetic population (read by app/modules/footprint/provider.py).

Runs after eval/build_dataset.py: profile pictures reuse face embeddings already computed there (the registry photo
for a genuine person, a fraudster's own selfie, a shared ring picture), so nothing is re-embedded.

What each kind of applicant looks like, as fraud teams describe it (and deliberately overlapping, not separable):
- genuine: an email used for years on several services; about half link an account in their name and photo.
  18% are new to digital life (a fresh email, almost no accounts): the check must stay neutral for them.
- first-party fraud: a real person lying about intent, so a real footprint. The footprint cannot catch it.
- synthetic / bot / ring: mostly fresh emails; 15% buy aged accounts; rings often share one profile picture.
- third-party (stolen identity) and tampered cards: the fraudster's own account, in their own name or face.
About 65% of applicants tick the optional consent, fraudsters a little less (declining is neutral).

Writes data/generated/footprint.json and footprint_photos.npz."""
import json
import pickle
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import GEN, PRE  # noqa: E402

rng = random.Random(11)


def iso(d: date) -> str:
    return d.isoformat()


def selfie_emb(app_id: str):
    p = PRE / "extract" / f"{app_id}.pkl"
    s = pickle.loads(p.read_bytes())["bio"]["selfie"] if p.exists() else None
    return None if not s else s["emb"]


def main():
    apps = json.loads((GEN / "population.json").read_text())
    reg_emb = dict(np.load(PRE / "registry_emb.npz"))
    names = [a["form"]["name"] for a in apps if a["label"] == 0]
    out = {"email": {}, "phone": {}, "linked": {}, "consent": {}}
    photos, ring_photo = {}, {}

    for a in apps:
        f, kind, today = a["form"], a["fraud_type"], datetime.fromisoformat(a["ts"]).date()
        dob = datetime.strptime(f["dob"], "%d/%m/%Y").date()
        adult_days = max(60, (today - dob).days - 12 * 365)  # an email can exist from about age 12
        real_person = kind in ("genuine", "hard_negative", "first_party")
        out["consent"][a["app_id"]] = rng.random() < (0.68 if real_person else 0.55)
        email = f["email"].lower()

        if real_person and rng.random() < 0.18:  # new to digital life
            out["email"][email] = {"first_seen": iso(today - timedelta(days=rng.randint(1, 300))), "services": rng.randint(0, 2)}
            continue
        if real_person:
            out["email"][email] = {"first_seen": iso(today - timedelta(days=rng.randint(400, min(adult_days, 15 * 365)))),
                                   "services": rng.randint(3, 14)}
            out["phone"].setdefault(f["phone"], {"first_seen": iso(today - timedelta(days=rng.randint(300, 3000))),
                                                 "services": rng.randint(2, 9)})
            if rng.random() < 0.55:
                full = rng.random() < 0.75
                # their own face: the registry photo for a genuine person, the applicant's selfie for first-party fraud
                key, pic = (f"reg_{f['id_number']}", reg_emb.get(f["id_number"])) if kind != "first_party" else \
                    (f"own_{a['app_id']}", selfie_emb(a["app_id"]))
                has_photo = rng.random() < 0.8 and pic is not None
                if has_photo:
                    photos[key] = pic
                out["linked"][email] = {"provider": rng.choice(["google", "linkedin"]),
                                        "name": f["name"] if full else f["name"].split()[0],
                                        "created": iso(today - timedelta(days=rng.randint(500, min(adult_days, 12 * 365)))),
                                        "photo": key if has_photo else None}
            continue

        aged = rng.random() < 0.15  # bought or recycled aged accounts
        out["email"][email] = {"first_seen": iso(today - timedelta(days=rng.randint(400, 2500) if aged else rng.randint(0, 45))),
                               "services": rng.randint(1, 4) if aged else rng.randint(0, 1)}
        if rng.random() > {"ring": 0.6, "bot": 0.2, "third_party": 0.5, "tampered": 0.25}.get(kind, 0.3):
            continue
        created = iso(today - timedelta(days=rng.randint(700, 2500) if aged else rng.randint(1, 60)))
        own = selfie_emb(a["app_id"])
        if kind == "ring":  # one picture reused across the ring, in each identity's own name
            g = a["group"] or a["app_id"]
            if g not in ring_photo and own is not None:
                ring_photo[g] = f"ring_{g}"
                photos[ring_photo[g]] = own
            key, name = ring_photo.get(g), f["name"]
        elif kind == "bot":  # a stock or stolen picture
            key = f"stock_{a['app_id']}"
            photos[key] = reg_emb[rng.choice(list(reg_emb))]
            name = f["name"]
        else:  # third_party / tampered: the fraudster's own account and face, often in their own name
            key = f"own_{a['app_id']}" if own is not None else None
            if key:
                photos[key] = own
            name = rng.choice(names) if kind == "third_party" and rng.random() < 0.7 else f["name"]
        out["linked"][email] = {"provider": rng.choice(["google", "linkedin"]), "name": name, "created": created,
                                "photo": key}

    (GEN / "footprint.json").write_text(json.dumps(out))
    np.savez(GEN / "footprint_photos.npz", **photos)
    print(f"footprint: {len(out['email'])} emails, {len(out['linked'])} linked accounts, {len(photos)} photos, "
          f"{sum(out['consent'].values())}/{len(out['consent'])} consented")


if __name__ == "__main__":
    main()
