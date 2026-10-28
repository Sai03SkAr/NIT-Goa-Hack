"""Supporting documents a lender collects beyond the ID card: electricity bill, salary slip, bank statement, cheque.

No issuer signs these, so they cannot be validated the way the card's QR is. TrueID checks what can be checked:
  - integrity: AI-generator markers and editing-software tags in the file's metadata (presence is strong, absence
    proves nothing), and the same image already submitted for a DIFFERENT applicant (perceptual hash)
  - legibility: resolution and sharpness, so a "fail" can be a retake request, not a fraud verdict
  - content: full-page OCR, then whether each value the applicant typed (name, consumer number, net pay...) is
    actually printed on the document
Every check returns a policy status (PASS / FAIL / UNAVAILABLE / NOT_PROVIDED); nothing here approves on its own."""
import hashlib
import re
import threading
from datetime import datetime

import cv2
import numpy as np
from rapidfuzz import fuzz
from sqlmodel import Field, SQLModel, select

from app import db
from app import policy as P
from app.modules.correlation.fuzzy import norm_token, tokens
from app.modules.document import forensics

KINDS = {
    "electricity_bill": "Electricity bill",
    "salary_slip": "Salary slip",
    "bank_statement": "Bank statement",
    "cheque": "Cancelled cheque",
    "other": "Document",
}
# claim field -> how to look for it in the OCR text
FIELD_TYPES = {"name": "name", "employer": "text", "consumer_no": "digits", "account_no": "digits", "pincode": "digits",
               "ifsc": "code", "bill_date": "date", "net_pay": "amount", "salary_credit": "amount", "month": "text",
               "provider": "text", "bank": "text"}
FIELD_LABELS = {"name": "Name", "employer": "Employer", "consumer_no": "Consumer number", "account_no": "Account number",
                "pincode": "PIN code", "ifsc": "IFSC", "bill_date": "Bill date", "net_pay": "Net pay",
                "salary_credit": "Salary credit", "month": "Pay month", "provider": "Provider", "bank": "Bank"}
# 32x32 dHash (1024 bits). Measured on the sample documents: the same file recompressed/resized 0-3 bits, two different
# people's bills from one template 15, unrelated documents ~80. The 8x8 hash could not tell two bills apart (1 bit).
# A re-photographed copy (~80) is NOT caught: only exact or digitally re-saved copies are.
REUSE_HAMMING, HASH_N = 6, 32
MIN_SIDE, MIN_SHARP = 500, 40.0


class DocPrint(SQLModel, table=True):
    """Fingerprint of every supporting document checked, so the same bill cannot back two different people."""
    id: int | None = Field(default=None, primary_key=True)
    sha256: str = Field(index=True)
    dhash: str = ""                       # 256 hex chars (32x32 difference hash)
    kind: str = ""
    owner: str = Field(default="", index=True)   # normalised applicant name the document was submitted for
    partner: str = ""
    ts: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class _Loader:
    """Loads a model once in a background thread. A request waits at most a couple of seconds for it, so a first-run
    model download (EasyOCR fetches its weights from the internet) never hangs an applicant's step: until the model is
    ready the dependent checks say UNAVAILABLE, never PASS."""

    def __init__(self, build):
        self.build, self.value, self.error = build, None, None
        self.ready, self._lock, self._started = threading.Event(), threading.Lock(), False

    def get(self, wait: float = 2.0):
        with self._lock:
            if not self._started:
                self._started = True
                threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(wait)
        return self.value

    def _run(self):
        try:
            self.value = self.build()
        except Exception as e:  # noqa: BLE001  shown as "unavailable", never as a pass
            self.error = f"{type(e).__name__}: {e}"[:160]
        self.ready.set()

    def why(self) -> str:
        return "Text reader is unavailable" + (f" ({self.error})" if self.error else ": its model is still loading")


def _build_page_reader():
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False)  # with the text detector: free-form pages, not a template


def _build_card_reader():
    from app.modules.document import ocr
    return ocr.reader()  # warms the recognition-only reader the card module uses


PAGE_OCR, CARD_OCR = _Loader(_build_page_reader), _Loader(_build_card_reader)


def page_text(img: np.ndarray) -> str | None:
    """All text on the page, upper-cased, or None when OCR is unavailable (never treated as 'nothing printed')."""
    reader = PAGE_OCR.get()
    if reader is None:
        return None
    try:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        s = 1600 / max(h, w)
        if s < 1:
            g = cv2.resize(g, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        return " ".join(reader.readtext(g, detail=0, paragraph=False)).upper()
    except Exception:
        return None


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _date_variants(v: str) -> list[str]:
    """'2026-10-02' or '02/10/2026' -> the ways a bill prints it."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", v) or None
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"^(\d{2})[/.-](\d{2})[/.-](\d{4})$", v)
        if not m:
            return [v.upper()]
        d, mo, y = m.groups()
    mon = datetime(int(y), int(mo), 1).strftime("%b").upper()
    return [f"{d}{mo}{y}", f"{d}{mo}{y[2:]}", f"{int(d)} {mon} {y}", f"{d} {mon} {y}", f"{d}-{mon}-{y}", f"{mon} {d}, {y}"]


def found(ftype: str, value: str, text: str) -> bool:
    v = str(value or "").strip()
    if not v:
        return False
    if ftype == "name":
        # every token of the claimed name printed somewhere (initials allowed), order-free
        words = {norm_token(w) for w in re.findall(r"[A-Z]+", text)}
        return all(any(t == w or (len(t) == 1 and w.startswith(t)) or (len(t) > 3 and fuzz.ratio(t, w) >= 85)
                       for w in words) for t in tokens(v))
    if ftype == "digits":
        d = _digits(v)
        return len(d) >= 4 and d in _digits(text)
    if ftype == "amount":  # "48,500.00" on the page vs "48500" typed: compare whole rupees as a standalone number
        whole = _digits(v.split(".")[0])
        return len(whole) >= 3 and whole in re.findall(r"\d+", text.replace(",", ""))
    if ftype == "date":
        flat, spaced = _digits(text), re.sub(r"\s+", " ", text)
        return any((x.isdigit() and x in flat) or (not x.isdigit() and x in spaced) for x in _date_variants(v))
    if ftype == "code":
        return v.upper().replace(" ", "") in text.replace(" ", "")
    return fuzz.partial_ratio(v.upper(), text) >= 85


def doc_hash(img: np.ndarray) -> str:
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (HASH_N + 1, HASH_N), interpolation=cv2.INTER_AREA)
    return f"{int(''.join('1' if b else '0' for b in (g[:, 1:] > g[:, :-1]).flatten()), 2):0{HASH_N * HASH_N // 4}x}"


def _hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1") if len(a) == len(b) else 10 ** 6


def owner_key(name: str) -> str:
    return " ".join(tokens(name or ""))


def reuse(sha: str, dh: str, owner: str) -> dict | None:
    """Earliest submission of the same image for a different applicant."""
    with db.session() as s:
        for r in s.exec(select(DocPrint).order_by(DocPrint.id)).all():
            if r.owner != owner and (r.sha256 == sha or (dh and r.dhash and _hamming(r.dhash, dh) <= REUSE_HAMMING)):
                return {"kind": r.kind, "ts": r.ts, "exact": r.sha256 == sha}
    return None


def remember(sha: str, dh: str, kind: str, owner: str, partner: str):
    with db.session() as s:
        if not s.exec(select(DocPrint).where(DocPrint.sha256 == sha, DocPrint.owner == owner)).first():
            s.add(DocPrint(sha256=sha, dhash=dh, kind=kind, owner=owner, partner=partner))
            s.commit()


def _c(check: str, label: str, status: str, detail: str = "") -> dict:
    return {"check": check, "label": label, "status": status, "detail": detail}


def integrity_checks(raw: bytes, img: np.ndarray, kind: str, owner: str, partner: str) -> list[dict]:
    out = []
    gm = forensics.genai_marker(raw)
    out.append(_c("ai_marker", "No AI-generator marker in the file",
                  P.FAIL if gm else P.PASS, f"Marker found: {gm}" if gm else "Metadata checked. Absence is not proof."))
    ed = forensics.exif_editor(raw)
    out.append(_c("editor_tag", "Not saved by photo-editing software",
                  P.FAIL if ed else P.PASS, f"Saved by {ed}" if ed else ""))
    sha, dh = hashlib.sha256(raw).hexdigest(), doc_hash(img)
    prior = reuse(sha, dh, owner)
    out.append(_c("reuse", "Not already used by another applicant", P.FAIL if prior else P.PASS,
                  (f"{'Identical' if prior['exact'] else 'Near-identical'} image submitted for someone else on "
                   f"{prior['ts'][:10]}") if prior else ""))
    remember(sha, dh, kind, owner, partner)
    return out


def quality_check(img: np.ndarray) -> dict:
    h, w = img.shape[:2]
    sharp = float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
    ok = min(h, w) >= MIN_SIDE and sharp >= MIN_SHARP
    return _c("legible", "Clear enough to read", P.PASS if ok else P.FAIL,
              "" if ok else f"{w}x{h}px, sharpness {sharp:.0f}: please retake in good light")


def check_supporting(kind: str, raw: bytes, img: np.ndarray, claims: dict, owner: str, partner: str,
                     read=None) -> dict:
    checks = [quality_check(img)] + integrity_checks(raw, img, kind, owner, partner)
    text = (read or page_text)(img)
    for field, value in claims.items():
        if field not in FIELD_TYPES or not str(value or "").strip():
            continue
        label = f"{FIELD_LABELS[field]} printed on the {KINDS.get(kind, 'document').lower()}"
        if text is None:
            checks.append(_c(f"text_{field}", label, P.UNAVAILABLE, PAGE_OCR.why()))
        else:
            checks.append(_c(f"text_{field}", label, P.PASS if found(FIELD_TYPES[field], value, text) else P.FAIL,
                             "" if found(FIELD_TYPES[field], value, text) else f"Couldn't find \"{value}\" on the page"))
    return {"kind": kind, "label": KINDS.get(kind, "Document"), "checks": checks, "ocr": text is not None}


SIG_LABEL = "Issuer signature on the card's QR is valid"


def check_id_card(raw: bytes, img: np.ndarray, form: dict, owner: str, partner: str) -> dict:
    """The ID card gets TrueID's document module: issuer-signed QR, QR vs print, card vs the e-KYC details, checksum.
    Reading and verifying the QR needs no downloaded model, so signature and identity checks always run; the
    QR-vs-print comparison needs the card OCR and says UNAVAILABLE until it has loaded."""
    from datetime import date
    from app.modules.correlation.fuzzy import name_sim
    from app.modules.document import agent as doc, checksums, qr_sign
    integrity = integrity_checks(raw, img, "id_card", owner, partner)
    if CARD_OCR.get() is not None:
        try:
            r = doc.assess(doc.extract(img, raw), form, date.today())
            st = lambda k: P.status(r.features, k)  # noqa: E731
            return {"kind": "id_card", "label": "ID card", "reasons": [x.code for x in r.reasons if x.weight > 0], "checks": [
                _c("doc_signature", SIG_LABEL, st("doc_signature")),
                _c("doc_consistency", "Signed QR agrees with the printed card", st("doc_consistency")),
                _c("form_consistency", "Card belongs to the person verified by Aadhaar", st("form_consistency")),
                _c("id_format", "ID number checksum", st("id_format"))] + integrity}
        except Exception:  # noqa: BLE001  fall through to the QR-only checks
            pass
    payload, qs = qr_sign.parse_and_verify(qr_sign.read_qr(img))
    sig = {qr_sign.VALID: (P.PASS, ""), qr_sign.NOT_FOUND: (P.NOT_PROVIDED, "No QR code found: retake with the whole card and QR in view"),
           qr_sign.NO_KEYS: (P.UNAVAILABLE, "No trusted issuer key configured")}.get(qs, (P.FAIL, f"QR signature check: {qs}"))
    checks = [_c("doc_signature", SIG_LABEL, *sig)]
    if qs == qr_sign.VALID:
        same = (name_sim(form["name"], payload["n"]) >= 0.8 and payload["d"] == form["dob"]
                and re.sub(r"\D", "", payload["id"]) == re.sub(r"\D", "", form["id_number"]))
        checks.append(_c("form_consistency", "Card belongs to the person verified by Aadhaar", P.PASS if same else P.FAIL,
                         "" if same else "The signed details on the card are for someone else"))
    else:
        checks.append(_c("form_consistency", "Card belongs to the person verified by Aadhaar", P.NOT_PROVIDED, "Needs a readable, signed QR"))
    checks.append(_c("doc_consistency", "Signed QR agrees with the printed card", P.UNAVAILABLE, CARD_OCR.why()))
    ck = checksums.verhoeff_valid(form["id_number"])
    checks.append(_c("id_format", "ID number checksum", P.PASS if ck else P.FAIL))
    return {"kind": "id_card", "label": "ID card", "checks": checks + integrity, "reasons": []}
