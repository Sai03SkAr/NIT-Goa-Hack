"""Digital-footprint sources. Used only when the applicant gives a separate, optional consent; never scraping.

What each field is and the licensed source that replaces the simulation in production:
- email:  first-seen date and how many online services know the address  -> an email-intelligence vendor
- phone:  first-seen date and how many online services know the number   -> a phone-intelligence vendor
          (the SIM's activation date already comes from the telecom registry)
- linked: an account the applicant CHOSE to sign in with on the partner's site (Google / LinkedIn OpenID Connect):
          the verified name, profile picture and account creation date the provider releases with that consent

The simulated source reads data/generated/footprint.json and footprint_photos.npz (data/gen_footprint.py).
TRUEID_FOOTPRINT_PROVIDER picks the source; until a licensed provider is wired in, any other value reports the
footprint as unavailable rather than inventing a result."""
import json
from functools import lru_cache

import numpy as np

from app.config import FOOTPRINT_PROVIDER, GEN


class FootprintUnavailable(Exception):
    """The source cannot answer (distinct from 'this person has no footprint')."""


@lru_cache(maxsize=1)
def _sim() -> dict | None:
    p = GEN / "footprint.json"
    try:
        d = json.loads(p.read_text()) if p.exists() else None
    except json.JSONDecodeError:
        return None
    if d is not None:
        ph = GEN / "footprint_photos.npz"
        d["photos"] = dict(np.load(ph)) if ph.exists() else {}
    return d


def lookup(email: str | None, phone: str | None) -> dict:
    """{'email': {first_seen, services} | None, 'phone': {...} | None,
        'linked': {provider, name, created, photo_emb} | None}. Dates are ISO strings."""
    if FOOTPRINT_PROVIDER != "simulated":
        raise FootprintUnavailable(f"no licensed footprint provider is configured for '{FOOTPRINT_PROVIDER}'")
    d = _sim()
    if d is None:
        raise FootprintUnavailable("simulated footprint data not built (data/gen_footprint.py)")
    e, ph = (email or "").strip().lower(), (phone or "").strip()
    linked = d["linked"].get(e) or d["linked"].get(ph)
    if linked:
        linked = {k: v for k, v in linked.items() if k != "photo"} | {"photo_emb": d["photos"].get(linked.get("photo") or "")}
    return {"email": d["email"].get(e), "phone": d["phone"].get(ph), "linked": linked}


def seeded_consent(app_id: str) -> bool:
    """Whether a seeded (synthetic) applicant ticked the optional footprint consent; decided by the data generator."""
    d = _sim()
    return bool(d and d.get("consent", {}).get(app_id))
