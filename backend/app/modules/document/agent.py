"""Document agent (D2): signed QR, 3-way consistency, checksums, date gate, forensics, TruFor (optional)."""
import time
from datetime import date

import cv2
import numpy as np

from app.modules.correlation.fuzzy import name_sim
from app.modules.document import card as C
from app.modules.document import checksums, dates, forensics, ocr, qr_sign, trufor
from app.schemas import ModuleResult, reason


def normalize(card_bgr: np.ndarray) -> np.ndarray:
    # shortcut: assumes a flat, template-aligned scan; add QR-anchored homography for phone photos
    return cv2.resize(card_bgr, (C.W, C.H), interpolation=cv2.INTER_AREA)


def extract(card_bgr: np.ndarray, raw: bytes | None = None, with_trufor=False) -> dict:
    norm = normalize(card_bgr)
    qr_text = qr_sign.read_qr(card_bgr)
    payload, sig_ok = qr_sign.parse_and_verify(qr_text)
    return {"qr_found": qr_text is not None, "qr_payload": payload, "qr_sig_ok": sig_ok,
            "ocr": ocr.read_fields(norm), "forensics": forensics.analyze(norm),
            "exif_editor": forensics.exif_editor(raw),
            "trufor": trufor.score(card_bgr) if with_trufor else None}


def assess(ext: dict, form: dict, today: date) -> ModuleResult:
    t0 = time.time()
    R, f = [], {}
    o = {k: v["text"] for k, v in ext["ocr"].items()}
    qp, sig_ok = ext["qr_payload"], ext["qr_sig_ok"]
    hard = 0.0

    f["doc_qr_missing"] = float(qp is None)
    f["doc_sig_invalid"] = float(qp is not None and not sig_ok)
    if qp is None:
        R.append(reason("DOC_QR_MISSING", 0.25))
    elif not sig_ok:
        R.append(reason("DOC_QR_SIG_INVALID", 0.5)); hard = 1.0

    # 3-way consistency: QR <-> OCR <-> form
    if qp is not None:
        f["doc_qr_ocr_name"] = name_sim(qp.get("n", ""), o["name"])
        f["doc_qr_ocr_dob"] = float(qp.get("d") == o["dob"])
        f["doc_qr_ocr_id4"] = float(qp.get("l4") == o["id_number"][-4:])
        if sig_ok and (f["doc_qr_ocr_name"] < 0.8 or not f["doc_qr_ocr_dob"]):
            R.append(reason("DOC_QR_OCR_MISMATCH", 0.5)); hard = 1.0
    else:
        f["doc_qr_ocr_name"] = f["doc_qr_ocr_dob"] = f["doc_qr_ocr_id4"] = np.nan
    trusted = {"name": qp["n"], "dob": qp["d"], "issue_date": qp["i"]} if (qp and sig_ok) else \
        {"name": o["name"], "dob": o["dob"], "issue_date": o["issue_date"]}
    f["doc_form_name"] = name_sim(form["name"], trusted["name"])
    f["doc_form_dob"] = float(form["dob"] == trusted["dob"])
    f["doc_form_id"] = float(form["id_number"] == o["id_number"])
    if f["doc_form_name"] < 0.8 or not f["doc_form_dob"]:
        R.append(reason("DOC_FORM_MISMATCH", 0.3))

    ck_ok = checksums.verhoeff_valid(form["id_number"])
    f["doc_checksum_ok"] = float(ck_ok)
    if not ck_ok:
        R.append(reason("DOC_CHECKSUM_FAIL", 0.5)); hard = 1.0
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
    ocr_conf = float(np.mean([v["conf"] for v in ext["ocr"].values()]))
    f["doc_ocr_conf"] = ocr_conf

    semantic = min(1.0, (1 - f["doc_form_name"]) + (1 - f["doc_form_dob"]) * 0.6 + f["doc_qr_missing"] * 0.4
                   + (0 if np.isnan(f["doc_qr_ocr_name"]) else (1 - f["doc_qr_ocr_name"]) + (1 - f["doc_qr_ocr_dob"])))
    parts = {"trufor": (0.5, tf), "semantic": (0.2, semantic), "font": (0.15, min(fz["font_dev"], 1)),
             "edge": (0.15, fz["score"])}
    avail = {k: v for k, v in parts.items() if v[1] is not None}
    soft = sum(w * x for w, x in avail.values()) / sum(w for w, _ in avail.values())
    risk = max(hard, soft)
    f["doc_risk"] = risk
    return ModuleResult(module="document", risk=round(risk, 3), confidence=round(min(1, ocr_conf + 0.2), 2),
                        reasons=R, features=f, latency_ms=int((time.time() - t0) * 1000),
                        evidence={"ocr": o, "qr": qp, "qr_signature_valid": sig_ok, "forensics": fz,
                                  "trufor": tf, "exif_editor": ext.get("exif_editor")})
