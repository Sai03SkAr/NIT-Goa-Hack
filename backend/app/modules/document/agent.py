"""Document agent (D2): signed QR, 3-way consistency, checksums, date gate, forensics, TruFor (optional)."""
import re
import time
from datetime import date

import cv2
import numpy as np

from app.modules.correlation.fuzzy import name_sim
from app.modules.document import card as C
from app.modules.document import aadhaar, checksums, dates, forensics, ocr, provenance, qr_sign, trufor
from app import policy as P
from app.schemas import ModuleResult, reason


_QR = cv2.QRCodeDetector()


def _qr_anchored(card_bgr: np.ndarray) -> np.ndarray | None:
    """Flatten a tilted / recaptured card: the QR's four detected corners are matched to where that exact QR sits on
    the template (rebuilt from its decoded text with the renderer's settings), giving a perspective transform."""
    import qrcode
    text, pts, _ = _QR.detectAndDecode(card_bgr)
    if not text or pts is None:
        return None
    src = pts.reshape(4, 2).astype(np.float32)
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=2, box_size=1)
    q.add_data(text)
    q.make(fit=True)
    side = C.QR_BOX[2] - C.QR_BOX[0]
    n = q.modules_count
    box = max(1, side // (n + 4))
    off = (side - (n + 4) * box) // 2
    x0, y0 = C.QR_BOX[0] + off + 2 * box, C.QR_BOX[1] + off + 2 * box
    x1, y1 = x0 + n * box, y0 + n * box
    dst = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    M = cv2.getPerspectiveTransform(src, dst)
    scale = abs(np.linalg.det(M[:2, :2]))
    if not 0.05 < scale < 20:  # degenerate corners: don't trust the warp
        return None
    return cv2.warpPerspective(card_bgr, M, (C.W, C.H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


OCR_SURE = 0.6  # edits are read at p5 0.69; blurry genuine misreads at median 0.41 (measured on the test split)
SIGNED_FIELDS = {"name": "n", "dob": "d", "id_number": "id", "gender": "g", "issue_date": "i"}


def _plausible(field: str, text: str) -> bool:
    t = re.sub(r"\s", "", text or "")
    if field == "id_number":
        return len(t) == 12 and t.isdigit() and checksums.verhoeff_valid(t)
    if field in ("dob", "issue_date"):
        return dates.parse(t) is not None
    return bool(t)


def normalize(card_bgr: np.ndarray, anchored: bool = False) -> np.ndarray:
    flat = _qr_anchored(card_bgr) if anchored else None
    return flat if flat is not None else cv2.resize(card_bgr, (C.W, C.H), interpolation=cv2.INTER_AREA)


def _best_reading(card_bgr: np.ndarray) -> tuple[np.ndarray, dict, str]:
    """OCR both a plain resize and the QR-anchored flattening; keep the more confident one.
    Measured on tilted test cards: never worse than either alone (mild tilt 10/10, moderate 7/10 vs 0/10)."""
    plain = normalize(card_bgr)
    best = (plain, ocr.read_fields(plain), "resize")
    flat = _qr_anchored(card_bgr)
    if flat is not None:
        f = ocr.read_fields(flat)
        conf = lambda r: float(np.mean([v["conf"] for v in r.values()]))
        if conf(f) > conf(best[1]):
            best = (flat, f, "qr_anchored")
    return best


_QR_CACHE: dict[str, dict] = {}


def card_qr(card_bgr: np.ndarray, raw: bytes | None = None) -> dict:
    """The card's QR, decoded and verified once per image (the document, face and registry steps all need it).
    {'kind': 'trueid' | 'aadhaar' | None, 'payload', 'status', 'extras'}; Aadhaar extras hold the signed photo."""
    import hashlib
    key = hashlib.sha256(raw if raw else card_bgr.tobytes()).hexdigest()
    if key not in _QR_CACHE:
        text = qr_sign.read_qr(card_bgr)
        if aadhaar.looks_like(text):
            payload, status, extras = aadhaar.parse_and_verify(text)
            out = {"kind": "aadhaar", "payload": payload, "status": status, "extras": extras}
        else:
            payload, status = qr_sign.parse_and_verify(text)
            out = {"kind": "trueid" if text else None, "payload": payload, "status": status, "extras": {}}
        if len(_QR_CACHE) > 64:
            _QR_CACHE.pop(next(iter(_QR_CACHE)))
        _QR_CACHE[key] = out
    return _QR_CACHE[key]


def extract(card_bgr: np.ndarray, raw: bytes | None = None, with_trufor=False) -> dict:
    q = card_qr(card_bgr, raw)
    payload, qr_status = q["payload"], q["status"]
    if q["kind"] == "aadhaar":  # a real Aadhaar: not our template, so read every printed line instead of fixed boxes
        norm = normalize(card_bgr)
        fields, how = {k: {"text": "", "conf": 0.0} for k in SIGNED_FIELDS}, "aadhaar_lines"
        lines = ocr.read_lines(card_bgr)
        # the pixel forensics compare against OUR template's texture and fonts: meaningless on a different layout
        forensic = {"score": 0.0, "tex_ratio": np.nan, "font_dev": 0.0, "contrast_dev": np.nan, "not_applicable": True}
    else:
        norm, fields, how = _best_reading(card_bgr)
        lines = None
        forensic = None
    return {"qr_found": q["kind"] is not None, "qr_payload": payload, "qr_status": qr_status, "qr_kind": q["kind"],
            "printed_lines": lines, "uidai_mobile_hash": (q["extras"] or {}).get("mobile_hash"),
            "uidai_photo": bool((q["extras"] or {}).get("photo")),
            "qr_sig_ok": qr_status == qr_sign.VALID, "normalized_by": how,
            "ocr": fields, "forensics": forensic or forensics.analyze(norm),
            "exif_editor": forensics.exif_editor(raw), "provenance": provenance.inspect(raw),
            "trufor": trufor.score(card_bgr) if with_trufor else None}


def _same(field: str, a: str, b: str) -> float:
    if field == "name":
        return name_sim(a, b)
    if field == "id_number":
        da, db = re.sub(r"\D", "", a or ""), re.sub(r"\D", "", b or "")
        if "X" in (a or "").upper() or "X" in (b or "").upper():  # a masked ID (Aadhaar QR): only the last 4 are known
            return float(len(da) >= 4 and len(db) >= 4 and da[-4:] == db[-4:])
        return float(da == db)
    return float((a or "").strip().upper() == (b or "").strip().upper())


def assess(ext: dict, form: dict, today: date) -> ModuleResult:
    t0 = time.time()
    R, f = [], {}
    o = {k: v["text"] for k, v in ext["ocr"].items()}
    conf = {k: v["conf"] for k, v in ext["ocr"].items()}
    qp, qs = ext["qr_payload"], ext.get("qr_status", qr_sign.VALID if ext.get("qr_sig_ok") else qr_sign.NOT_FOUND)
    sig_ok = qs == qr_sign.VALID
    hard = 0.0

    # signature: only VALID means the issuer signed exactly these fields
    f["doc_qr_missing"] = float(qs == qr_sign.NOT_FOUND)
    f["doc_sig_invalid"] = float(qs in (qr_sign.INVALID_SIG, qr_sign.UNTRUSTED_KEY, qr_sign.MALFORMED))
    if qs == qr_sign.NOT_FOUND:
        R.append(reason("DOC_QR_MISSING", 0.25)); ev_sig = P.NOT_PROVIDED
    elif qs == qr_sign.NO_KEYS:
        R.append(reason("DOC_QR_UNVERIFIABLE", 0.2)); ev_sig = P.UNAVAILABLE
    elif not sig_ok:
        R.append(reason("DOC_QR_SIG_INVALID", 0.5)); hard = 1.0; ev_sig = P.FAIL
    else:
        ev_sig = P.PASS
    f["ev_doc_signature"] = P.CODE[ev_sig]

    aadhaar_card = ext.get("qr_kind") == "aadhaar"
    if aadhaar_card:
        R.append(reason("DOC_UIDAI_QR", 0.0))
    # signed QR <-> printed card (OCR), field by field, with OCR-confidence gating
    for k, q in SIGNED_FIELDS.items():
        if aadhaar_card:
            f[f"doc_ocr_conf_{k}"], f[f"doc_qr_ocr_{k}"] = 0.0, np.nan
            continue
        f[f"doc_ocr_conf_{k}"] = conf[k]
        f[f"doc_qr_ocr_{k}"] = _same(k, qp[q], o[k]) if sig_ok else np.nan
    if sig_ok and aadhaar_card:
        ev_cons = _aadhaar_print_check(ext.get("printed_lines") or [], qp, R)
    elif sig_ok:
        bad = [k for k in SIGNED_FIELDS if (f[f"doc_qr_ocr_{k}"] < 0.8 if k == "name" else f[f"doc_qr_ocr_{k}"] == 0)]
        # an edit is a confident read of a value that could be real: a misread digit breaks the ID checksum and a
        # misread date does not parse, but a forger's printed replacement passes both (measured: genuine card
        # misread '6'->'3' in the ID at conf 0.79 was hard-rejected before this check)
        sure = [k for k in bad if conf[k] >= OCR_SURE and _plausible(k, o[k])]
        if not bad:
            ev_cons = P.PASS
        elif sure:
            R.append(reason("DOC_QR_OCR_MISMATCH", 0.5)); hard = 1.0; ev_cons = P.FAIL
        else:  # barely readable print: not evidence of an edit; neutral for the model, a human/recapture decides
            R.append(reason("DOC_OCR_UNREADABLE", 0.2)); ev_cons = P.UNAVAILABLE
            f["doc_qr_ocr_unsure"] = 1.0
            for k in bad:
                f[f"doc_qr_ocr_{k}"] = 1.0
    else:
        ev_cons = P.NOT_PROVIDED
    f["ev_doc_consistency"] = P.CODE[ev_cons]

    # form <-> card (signed values when available, otherwise the printed text)
    trusted = {k: (qp[q] if sig_ok else o[k]) for k, q in SIGNED_FIELDS.items()}
    f["doc_form_name"] = name_sim(form["name"], trusted["name"])
    f["doc_form_dob"] = float(form["dob"] == trusted["dob"])
    f["doc_form_id"] = _same("id_number", form["id_number"], trusted["id_number"])
    form_ok = f["doc_form_name"] >= 0.8 and f["doc_form_dob"] == 1 and f["doc_form_id"] == 1
    if not form_ok:
        R.append(reason("DOC_FORM_MISMATCH", 0.3))
    f["ev_form_consistency"] = P.CODE[P.PASS if form_ok else P.FAIL]

    if aadhaar_card and sig_ok and ext.get("uidai_mobile_hash") is not None:  # informational: numbers change
        linked = aadhaar.hash_matches(form.get("phone", ""), ext["uidai_mobile_hash"], qp.get("id_last4", "0")[-1:] or "0")
        f["doc_uidai_mobile_linked"] = float(bool(linked))
        if linked is False:
            R.append(reason("DOC_UIDAI_MOBILE_OTHER", 0.05))

    ck_ok = checksums.verhoeff_valid(form["id_number"])
    f["doc_checksum_ok"] = float(ck_ok)
    if not ck_ok:  # could be a typo: review, not an automatic fraud verdict
        R.append(reason("DOC_CHECKSUM_FAIL", 0.5))
    f["ev_id_format"] = P.CODE[P.PASS if ck_ok else P.FAIL]
    pan_ok, _ = checksums.pan_valid(form.get("pan", ""), form["name"].split()[-1])
    f["doc_pan_ok"] = float(pan_ok)
    if not pan_ok:
        R.append(reason("DOC_PAN_FORMAT", 0.2))

    viol = dates.date_gate(trusted["dob"], trusted["issue_date"], today)
    f["doc_date_violations"] = float(len(viol))
    if viol and viol != ["dob_unreadable"]:
        R.append(reason("DOC_DATE_INVALID", 0.3))

    fz = ext["forensics"]
    f.update({"doc_tex_ratio": fz["tex_ratio"], "doc_font_dev": fz["font_dev"], "doc_contrast_dev": fz["contrast_dev"],
              "doc_forensic": fz["score"]})
    if fz["score"] > 0.45:
        R.append(reason("DOC_FORENSIC_ANOMALY", fz["score"] * 0.3))
    tf = ext.get("trufor")
    f["doc_trufor"] = tf if tf is not None else np.nan
    if tf is not None and tf > 0.6:
        R.append(reason("DOC_TRUFOR_HIGH", tf * 0.3))
    if ext.get("exif_editor"):
        R.append(reason("DOC_EXIF_EDITOR", 0.1))
    prov = ext.get("provenance") or {"ai": ext.get("genai_marker")}
    f["meta_genai_card"] = float(bool(prov.get("ai")))  # 'meta_' = policy only, never a model feature
    if prov.get("ai"):
        R.append(reason("DOC_GENAI_METADATA", 0.4))
    ocr_conf = float(np.mean(list(conf.values()))) if not aadhaar_card else \
        float(np.mean(sorted([x["conf"] for x in ext.get("printed_lines") or []], reverse=True)[:5] or [0.0]))  # the clearest lines
    f["doc_ocr_conf"] = ocr_conf

    cons = [f[f"doc_qr_ocr_{k}"] for k in SIGNED_FIELDS if not np.isnan(f[f"doc_qr_ocr_{k}"])]
    semantic = min(1.0, (1 - f["doc_form_name"]) + (1 - f["doc_form_dob"]) * 0.6 + (1 - f["doc_form_id"]) * 0.6
                   + f["doc_qr_missing"] * 0.4 + sum(1 - c for c in cons))
    parts = {"semantic": (0.4, semantic), "font": (0.3, min(fz["font_dev"], 1)), "edge": (0.3, fz["score"])}
    soft = sum(w * x for w, x in parts.values()) / sum(w for w, _ in parts.values())
    risk = max(hard, soft)
    f["doc_risk"] = risk
    return ModuleResult(module="document", risk=round(risk, 3), confidence=round(min(1, ocr_conf + 0.2), 2),
                        reasons=R, features=f, latency_ms=int((time.time() - t0) * 1000),
                        evidence={"ocr": o, "ocr_conf": conf, "qr": qp, "qr_status": qs, "qr_signature_valid": sig_ok,
                                  "forensics": fz, "trufor": tf, "exif_editor": ext.get("exif_editor"),
                                  "genai_marker": prov.get("ai"), "provenance": prov,
                                  "normalized_by": ext.get("normalized_by"), "qr_kind": ext.get("qr_kind"),
                                  "printed_lines": [x["text"] for x in ext.get("printed_lines") or []][:20] or None,
                                  "uidai_mobile_linked": None if "doc_uidai_mobile_linked" not in f else bool(f["doc_uidai_mobile_linked"])})


def _aadhaar_print_check(lines: list[dict], qp: dict, R: list) -> str:
    """Does the printed Aadhaar show the name, date of birth and last 4 digits that UIDAI signed? Layout-free, so a
    miss means "a person should compare" (UNAVAILABLE), never an automatic forgery verdict."""
    text = [x["text"] for x in lines if x["conf"] >= 0.3]
    joined = " ".join(text)
    name_ok = any(name_sim(qp["n"], t.upper()) >= 0.8 for t in text)
    dob_ok = bool(qp["d"]) and re.sub(r"\D", "", qp["d"]) in re.sub(r"\D", "", joined)
    id_ok = bool(qp.get("id_last4")) and qp["id_last4"] in re.sub(r"\s", "", joined)
    if name_ok and dob_ok and id_ok:
        return P.PASS
    R.append(reason("DOC_OCR_UNREADABLE", 0.1))
    return P.UNAVAILABLE
