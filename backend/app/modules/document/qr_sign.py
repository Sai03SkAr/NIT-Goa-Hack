"""Mock issuer: signs card payloads with Ed25519 (like UIDAI Secure QR). A forger can copy pixels, not the key."""
import base64
import json

import cv2
import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.config import KEYS

PREFIX = "TID1"


def _load_or_create(name: str) -> Ed25519PrivateKey:
    path = KEYS / f"{name}.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    return key


def issuer_key() -> Ed25519PrivateKey:
    return _load_or_create("issuer")


def forger_key() -> Ed25519PrivateKey:
    """Key a fraudster would use to fake a QR; never trusted by the verifier."""
    return _load_or_create("forger")


def issuer_public() -> Ed25519PublicKey:
    return issuer_key().public_key()


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def make_qr_text(payload: dict, key: Ed25519PrivateKey | None = None) -> str:
    key = key or issuer_key()
    body = canonical(payload)
    sig = key.sign(body)
    return f"{PREFIX}|{base64.urlsafe_b64encode(body).decode()}|{base64.urlsafe_b64encode(sig).decode()}"


def parse_and_verify(text: str | None) -> tuple[dict | None, bool]:
    """Returns (payload or None, signature_valid)."""
    if not text or not text.startswith(PREFIX + "|"):
        return None, False
    try:
        _, b, s = text.split("|")
        body, sig = base64.urlsafe_b64decode(b), base64.urlsafe_b64decode(s)
        payload = json.loads(body)
    except Exception:
        return None, False
    try:
        issuer_public().verify(sig, body)
        return payload, True
    except InvalidSignature:
        return payload, False


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
