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
