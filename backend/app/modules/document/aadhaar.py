"""Real Aadhaar cards: UIDAI Secure QR (offline verification).

Aadhaar letters, PVC cards and e-Aadhaar PDFs issued since 2019 carry a Secure QR. Its content is one large decimal
number. As bytes, it is GZip-compressed data with fields separated by byte 255:
    [version "V2".."V5",] email/mobile indicator, reference id (last 4 Aadhaar digits + timestamp), name, date of
    birth, gender, care of, district, landmark, house, location, pincode, post office, state, street, sub-district,
    village/town/city, [last 4 mobile digits,] JPEG2000 photo, [email hash], [mobile hash], 256-byte RSA signature
The signature (RSA-2048, SHA-256, PKCS#1 v1.5) covers everything before it and verifies against UIDAI's public
certificate. That makes the name, DOB, gender, address and photo issuer-attested without calling UIDAI, which is the
offline Aadhaar verification RBI accepts for KYC.

The certificate is not shipped in the repository: download UIDAI's current Secure QR certificate from uidai.gov.in
and put the .cer / .pem in data/issuer_keys/uidai/ (or point TRUEID_UIDAI_CERT at it). Without it the QR is still
read, but reported as unverifiable, never as valid.

Privacy: only the last 4 Aadhaar digits are in the QR. The photo is kept only as a face embedding and a short-lived
upload file; the mobile and email hashes are checked and never stored.
Older (pre-2019) Aadhaar QRs are plain unsigned XML: read for convenience, reported as unverifiable.
"""
import hashlib
import os
import re
import zlib
from datetime import datetime
from xml.etree import ElementTree

from app.config import KEYS
from app.modules.document.qr_sign import INVALID_SIG, MALFORMED, NO_KEYS, VALID

OLD_FIELDS = ["indicator", "reference_id", "name", "dob", "gender", "care_of", "district", "landmark", "house",
              "location", "pincode", "post_office", "state", "street", "sub_district", "vtc"]
NEW_FIELDS = ["version"] + OLD_FIELDS + ["mobile_last4"]
SIG_LEN, HASH_LEN = 256, 32
CERT_DIR = KEYS / "uidai"


def looks_like(text: str | None) -> bool:
    t = (text or "").strip()
    return (len(t) > 300 and t.isdigit()) or t.startswith("<?xml") and "PrintLetterBarcodeData" in t[:400] \
        or t.startswith("<PrintLetterBarcodeData")


def _dob(s: str) -> str:
    s = s.strip().replace("-", "/").replace(".", "/")
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", s):  # YYYY/MM/DD
        y, m, d = s.split("/")
        return f"{d}/{m}/{y}"
    return s  # DD/MM/YYYY, or a bare year for people whose full date is not on record


def _ts(ref: str) -> str:
    try:
        return datetime.strptime(ref[4:18], "%Y%m%d%H%M%S").strftime("%d/%m/%Y")
    except ValueError:
        return ""


def decompress(text: str) -> bytes:
    n = int(text.strip())
    return zlib.decompress(n.to_bytes((n.bit_length() + 7) // 8, "big"), 16 + zlib.MAX_WBITS)


def split(data: bytes) -> dict:
    """Text fields, photo bytes, hashes and signature. Raises ValueError on anything that does not fit the layout."""
    first = data[:data.index(255)] if 255 in data[:8] else b""
    names = NEW_FIELDS if re.fullmatch(rb"V\d", first) else OLD_FIELDS
    pos, fields = 0, {}
    for name in names:
        end = data.index(255, pos)
        raw = data[pos:end]
        try:
            fields[name] = raw.decode("utf-8")
        except UnicodeDecodeError:
            fields[name] = raw.decode("iso-8859-1")
        pos = end + 1
    ind = int(fields["indicator"] or 0)
    if ind not in (0, 1, 2, 3):
        raise ValueError("bad email/mobile indicator")
    n_hash = {0: 0, 1: 1, 2: 1, 3: 2}[ind]
    tail = SIG_LEN + n_hash * HASH_LEN
    if len(data) - pos < tail:
        raise ValueError("too short")
    sig = data[-SIG_LEN:]
    hashes = data[len(data) - tail:-SIG_LEN]
    mobile = email = None
    if ind == 3:
        email, mobile = hashes[:HASH_LEN], hashes[HASH_LEN:]
    elif ind == 2:
        mobile = hashes
    elif ind == 1:
        email = hashes
    return {"fields": fields, "photo": data[pos:len(data) - tail], "email_hash": email, "mobile_hash": mobile,
            "signed": data[:-SIG_LEN], "signature": sig}


def certificates():
    from cryptography import x509
    paths = [p for p in CERT_DIR.glob("*") if p.suffix.lower() in (".cer", ".crt", ".pem")] if CERT_DIR.exists() else []
    if os.getenv("TRUEID_UIDAI_CERT"):
        from pathlib import Path
        paths.append(Path(os.environ["TRUEID_UIDAI_CERT"]))
    out = []
    for p in paths:
        b = p.read_bytes()
        try:
            out.append(x509.load_pem_x509_certificate(b) if b"BEGIN CERTIFICATE" in b else x509.load_der_x509_certificate(b))
        except ValueError:
            continue
    return out


def verify(signed: bytes, sig: bytes) -> tuple[str, str | None]:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    certs = certificates()
    if not certs:
        return NO_KEYS, None
    for c in certs:
        try:
            c.public_key().verify(sig, signed, padding.PKCS1v15(), hashes.SHA256())
            return VALID, c.subject.rfc4514_string()
        except (InvalidSignature, ValueError, TypeError):
            continue
    return INVALID_SIG, None


def hash_matches(value: str, stored: bytes | None, last_digit: str) -> bool | None:
    """UIDAI hashes the mobile number (or email) with SHA-256 repeated n times, n = last Aadhaar digit (0 or 1 -> once)."""
    if stored is None or not value:
        return None
    n = int(last_digit) if last_digit.isdigit() and int(last_digit) > 1 else 1
    h = value.strip()
    for _ in range(n):
        h = hashlib.sha256(h.encode()).hexdigest()
    return h == stored.hex()


def payload_of(fields: dict, issuer: str) -> dict:
    """In the shape the document agent compares (n, d, id, g, i), plus the Aadhaar-only extras."""
    ref = fields.get("reference_id", "")
    last4 = ref[:4] if ref[:4].isdigit() else ""
    addr = {k: fields.get(k, "") for k in ("care_of", "house", "street", "landmark", "location", "vtc", "post_office",
                                           "sub_district", "district", "state", "pincode") if fields.get(k)}
    return {"n": fields.get("name", "").upper(), "d": _dob(fields.get("dob", "")), "id": "XXXXXXXX" + last4,
            "g": (fields.get("gender") or "")[:1].upper(), "i": _ts(ref), "kid": "uidai", "issuer": issuer,
            "format": fields.get("version") or "secure-qr-2019", "id_last4": last4, "address": addr,
            "mobile_last4": fields.get("mobile_last4") or None}


def parse_and_verify(text: str) -> tuple[dict | None, str, dict]:
    """(payload, status, extras). extras: {'photo': JPEG2000 bytes, 'mobile_hash', 'email_hash'}, never persisted."""
    t = text.strip()
    if t.startswith("<"):  # pre-2019 QR: unsigned XML, so it can't be verified however genuine it is
        try:
            x = ElementTree.fromstring(t[t.index("<PrintLetterBarcodeData"):] if "<?xml" in t[:10] else t)
        except (ElementTree.ParseError, ValueError):
            return None, MALFORMED, {}
        a = x.attrib
        f = {"name": a.get("name", ""), "dob": a.get("dob") or a.get("yob", ""), "gender": a.get("gender", ""),
             "reference_id": (a.get("uid") or "")[-4:], "pincode": a.get("pc", ""), "state": a.get("state", ""),
             "vtc": a.get("vtc", ""), "district": a.get("dist", ""), "house": a.get("house", ""), "street": a.get("street", "")}
        p = payload_of(f, "UIDAI (unsigned pre-2019 QR)")
        p["format"] = "xml-unsigned"
        return p, NO_KEYS, {}
    try:
        parts = split(decompress(t))
    except (ValueError, zlib.error, OverflowError):
        return None, MALFORMED, {}
    status, signer = verify(parts["signed"], parts["signature"])
    p = payload_of(parts["fields"], "UIDAI" + (f" ({signer})" if signer else ""))
    return p, status, {"photo": parts["photo"], "mobile_hash": parts["mobile_hash"], "email_hash": parts["email_hash"]}


def photo_bgr(jp2: bytes | None):
    """Decode the QR's JPEG2000 photo to an OpenCV image (None if absent or undecodable)."""
    if not jp2:
        return None
    import io

    import cv2
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(jp2)).convert("RGB")
    except Exception:
        return None
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def make_secure_qr(fields: dict, photo_jp2: bytes, private_key, version: str = "V2", mobile: str | None = None,
                   email: str | None = None) -> str:
    """Build a Secure QR number in UIDAI's layout. FOR TESTS: signed with a test key, never UIDAI's."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    last = fields["reference_id"][3]
    hx = lambda v: bytes.fromhex(_chain(v, last))  # noqa: E731
    ind = (1 if email else 0) + (2 if mobile else 0)
    names = NEW_FIELDS if version else OLD_FIELDS
    vals = {**fields, "indicator": str(ind), "version": version or "", "mobile_last4": (mobile or "")[-4:]}
    body = b"".join(str(vals.get(k, "")).encode() + b"\xff" for k in names) + photo_jp2
    body += (hx(email) if email else b"") + (hx(mobile) if mobile else b"")
    sig = private_key.sign(body, padding.PKCS1v15(), hashes.SHA256())
    gz = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    blob = gz.compress(body + sig) + gz.flush()
    return str(int.from_bytes(blob, "big"))


def _chain(value: str, last_digit: str) -> str:
    n = int(last_digit) if int(last_digit) > 1 else 1
    h = value
    for _ in range(n):
        h = hashlib.sha256(h.encode()).hexdigest()
    return h

