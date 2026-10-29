"""EasyOCR on the template's field boxes (recognition only, no detector: fast on CPU)."""
import re
from functools import lru_cache

import cv2
import numpy as np

from app.modules.document.card import FIELD_BOXES

ALLOW = {"name": "ABCDEFGHIJKLMNOPQRSTUVWXYZ .", "dob": "0123456789/", "issue_date": "0123456789/",
         "id_number": "0123456789 ", "gender": "MALEFMALE"}


@lru_cache(maxsize=1)
def reader():
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False, detector=False)  # recognition-only on template boxes


def read_fields(card_norm_bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(card_norm_bgr, cv2.COLOR_BGR2GRAY)
    out = {}
    for k, (x0, y0, x1, y1) in FIELD_BOXES.items():
        pad = 6
        res = reader().recognize(gray, horizontal_list=[[x0 - pad, x1 + pad, y0 - pad, y1 + pad]], free_list=[],
                                 allowlist=ALLOW[k], detail=1)
        text, conf = (res[0][1], float(res[0][2])) if res else ("", 0.0)
        out[k] = {"text": clean(k, text), "conf": round(conf, 3)}
    return out


def read_lines(img_bgr: np.ndarray, max_lines: int = 40) -> list[dict]:
    """Every text line on a card whose layout we don't know: lines are found by dilating ink horizontally, then
    each is read by the same recogniser (no detector model needed). [{'text', 'conf'}], top to bottom."""
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    if max(g.shape) > 1600:
        s = 1600 / max(g.shape)
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    blob = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, g.shape[1] // 40), 3)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(blob)
    boxes = []
    for x, y, w, h, area in stats[1:]:
        if 10 <= h <= g.shape[0] // 6 and w >= 2 * h and w > 30:  # text-line shaped, not a photo or the QR
            boxes.append([int(x) - 4, int(x + w) + 4, int(y) - 3, int(y + h) + 3])
    boxes = sorted(boxes, key=lambda b: (b[2], b[0]))[:max_lines]
    if not boxes:
        return []
    res = reader().recognize(g, horizontal_list=boxes, free_list=[], detail=1)
    return [{"text": t.strip(), "conf": round(float(c), 3)} for _, t, c in res if t.strip()]


def clean(field: str, t: str) -> str:
    t = t.strip()
    if field == "id_number":
        return re.sub(r"\D", "", t)
    if field in ("dob", "issue_date"):
        d = re.sub(r"\D", "", t)
        return f"{d[:2]}/{d[2:4]}/{d[4:8]}" if len(d) == 8 else t
    if field == "gender":
        return "F" if t.upper().startswith("F") else ("M" if t.upper().startswith("M") else "")
    return re.sub(r"\s+", " ", t).upper()
