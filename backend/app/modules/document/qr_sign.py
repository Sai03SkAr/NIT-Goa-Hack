"""Fictional issuer QR (SPECIMEN cards only; this is NOT Aadhaar Secure QR).

Schema v2:  "TID2|" + base64url(canonical JSON) + "|" + base64url(Ed25519 signature)
  payload = {"v": 2, "kid": key id, "n": NAME, "d": DD/MM/YYYY, "g": M|F, "id": 12-digit specimen ID, "i": DD/MM/YYYY}
The full ID binds the card to one identity (v1 carried only the last 4 digits, which collide across people).

Roles are separate: generators sign with the issuer PRIVATE key; the verifier only loads allow-listed PUBLIC keys
(data/issuer_keys/<kid>.pub) and never creates keys. No trusted key configured -> verification UNAVAILABLE."""
import base64
import json
import re

import cv2
import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.config import KEYS

PREFIX = "TID2"
KID = "demo-1"
VALID, INVALID_SIG, UNTRUSTED_KEY, MALFORMED, NOT_FOUND, NO_KEYS = (
    "VALID", "INVALID_SIGNATURE", "UNTRUSTED_KEY", "MALFORMED", "NOT_FOUND", "NO_TRUSTED_KEYS")
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_FIELDS = {"v": lambda x: x == 2, "kid": lambda x: isinstance(x, str) and 0 < len(x) <= 16,
           "n": lambda x: isinstance(x, str) and 0 < len(x) <= 60 and re.fullmatch(r"[A-Z .'\-]+", x) is not None,
           "d": lambda x: isinstance(x, str) and _DATE.match(x) is not None,
           "g": lambda x: x in ("M", "F"),
           "id": lambda x: isinstance(x, str) and re.fullmatch(r"\d{12}", x) is not None,
           "i": lambda x: isinstance(x, str) and _DATE.match(x) is not None}


# ---------------------------------------------------------------- issuer side (generators / demo kits only)
def _load_or_create_private(name: str) -> Ed25519PrivateKey:
    path = KEYS / f"{name}.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(0o600)
    return key


def issuer_key() -> Ed25519PrivateKey:
    key = _load_or_create_private("issuer")
    pub = KEYS / f"{KID}.pub"
    if not pub.exists():  # publish the matching public key for the verifier
        pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return key


def forger_key() -> Ed25519PrivateKey:
    """Key a fraudster would use; its public key is never published, so its QRs never verify."""
    return _load_or_create_private("forger")


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def make_qr_text(fields: dict, key: Ed25519PrivateKey | None = None, kid: str = KID) -> str:
    """fields: n, d, g, id, i (see module doc)."""
    payload = {"v": 2, "kid": kid, **{k: fields[k] for k in ("n", "d", "g", "id", "i")}}
    body = canonical(payload)
    sig = (key or issuer_key()).sign(body)
    return f"{PREFIX}|{base64.urlsafe_b64encode(body).decode()}|{base64.urlsafe_b64encode(sig).decode()}"


# ---------------------------------------------------------------- verifier side
def trusted_keys() -> dict[str, Ed25519PublicKey]:
    keys = {}
    for p in KEYS.glob("*.pub"):
        try:
            keys[p.stem] = serialization.load_pem_public_key(p.read_bytes())
        except ValueError:
            continue
    return keys


def parse_and_verify(text: str | None) -> tuple[dict | None, str]:
    """Returns (payload if structurally valid, status). Only VALID means the issuer signed exactly these fields."""
    if not text:
        return None, NOT_FOUND
    parts = text.split("|")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None, MALFORMED
    try:
        body, sig = base64.urlsafe_b64decode(parts[1]), base64.urlsafe_b64decode(parts[2])
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None, MALFORMED
    if not isinstance(payload, dict) or set(payload) != set(_FIELDS) or not all(ok(payload[k]) for k, ok in _FIELDS.items()) \
            or len(sig) != 64 or body != canonical(payload):
        return None, MALFORMED
    keys = trusted_keys()
    if not keys:
        return payload, NO_KEYS
    pub = keys.get(payload["kid"])
    if pub is None:
        return payload, UNTRUSTED_KEY
    try:
        pub.verify(sig, body)
        return payload, VALID
    except InvalidSignature:
        return payload, INVALID_SIG


_DETECTORS = [cv2.QRCodeDetector(), cv2.QRCodeDetectorAruco()]


def _candidates(img_bgr: np.ndarray):
    from app.modules.document.card import H, QR_BOX, W
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    norm = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA)
    pad = 25
    crop = norm[QR_BOX[1] - pad:QR_BOX[3] + pad, QR_BOX[0] - pad:min(W, QR_BOX[2] + pad)]
    up = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    yield up
    yield cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    yield g  # card not on the template grid: search the whole image


def read_qr(img_bgr: np.ndarray) -> str | None:
    for im in _candidates(img_bgr):
        for det in _DETECTORS:
            try:
                text, _, _ = det.detectAndDecode(im)
            except cv2.error:
                continue
            if text:
                return text
    return None
