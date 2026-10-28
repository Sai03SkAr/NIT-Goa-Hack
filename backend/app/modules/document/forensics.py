"""Cheap forensics (DeepID Reagvis/Hardik style): background texture, stroke/font consistency, contrast, ELA visual.
Each field box is compared with the other fields of the same card, so the signal is relative, not absolute."""
import io

import cv2
import numpy as np
from PIL import Image

from app.modules.document.card import FIELD_BOXES


def _field_stats(gray: np.ndarray, box) -> dict:
    x0, y0, x1, y1 = box
    roi = gray[y0:y1, x0:x1].astype(np.float32)
    thr = cv2.threshold(roi.astype(np.uint8), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    ink = thr > 0
    bg = ~cv2.dilate(thr, np.ones((5, 5), np.uint8)).astype(bool)
    hp = roi - cv2.GaussianBlur(roi, (0, 0), 3)
    bg_tex = float(hp[bg].std()) if bg.sum() > 50 else 0.0
    edges = cv2.Canny(roi.astype(np.uint8), 40, 120)
    stroke = 0.0
    if ink.sum() > 20:
        dt = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 3)
        stroke = float(dt[ink].mean())
    contrast = float(np.median(roi[bg]) - np.median(roi[ink])) if ink.sum() > 20 and bg.sum() > 50 else 0.0
    return {"bg_tex": bg_tex, "edge": float((edges > 0).mean()), "stroke": stroke, "contrast": contrast}


def analyze(card_norm_bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(card_norm_bgr, cv2.COLOR_BGR2GRAY)
    st = {k: _field_stats(gray, b) for k, b in FIELD_BOXES.items()}

    def rel_dev(key):
        v = np.array([s[key] for s in st.values()])
        med = np.median(v) + 1e-6
        return np.abs(v - med) / med

    tex = np.array([s["bg_tex"] for s in st.values()])
    tex_ratio = float(tex.min() / (np.median(tex) + 1e-6))      # an edited box has lost the guilloche texture
    font_dev = float(rel_dev("stroke").max())
    contrast_dev = float(rel_dev("contrast").max())
    edge_dev = float(rel_dev("edge").max())
    worst = list(st)[int(np.argmin(tex))]
    score = float(np.clip(0.45 * max(0, 0.75 - tex_ratio) / 0.75 + 0.25 * min(font_dev, 1)
                          + 0.15 * min(contrast_dev, 1) + 0.15 * min(edge_dev, 1), 0, 1))
    return {"tex_ratio": round(tex_ratio, 3), "font_dev": round(font_dev, 3), "contrast_dev": round(contrast_dev, 3),
            "edge_dev": round(edge_dev, 3), "worst_field": worst, "score": round(score, 3)}


def ela_heatmap(card_bgr: np.ndarray, quality=90) -> np.ndarray:
    """Error Level Analysis, visual only (weak signal; never fused)."""
    ok, enc = cv2.imencode(".jpg", card_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    re = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(card_bgr, re).astype(np.float32).max(axis=2)
    diff = cv2.GaussianBlur(diff, (0, 0), 2)
    diff = (255 * diff / (diff.max() + 1e-6)).astype(np.uint8)
    heat = cv2.applyColorMap(diff, cv2.COLORMAP_INFERNO)
    return cv2.addWeighted(card_bgr, 0.5, heat, 0.5, 0)


# IPTC "digital source type" values that generators (and honest editors) write for AI-made media, plus generator names
GENAI_MARKERS = (b"trainedalgorithmicmedia", b"compositewithtrainedalgorithmicmedia", b"algorithmicmedia",
                 b"midjourney", b"dall-e", b"dall\xc2\xb7e", b"stable diffusion", b"stablediffusion", b"adobe firefly",
                 b"gpt-image", b"imagen", b"flux.1", b"ideogram", b"leonardo.ai")


def genai_marker(raw: bytes | None) -> str | None:
    """Generator / AI-provenance marker in the file's metadata. Presence is strong; ABSENCE PROVES NOTHING
    (metadata is trivially stripped). C2PA alone is not a marker: real phone cameras sign photos with it too."""
    if not raw:
        return None
    blob = raw[:262144].lower()  # metadata segments sit at the start of JPEG/PNG/WebP files
    return next((m.decode("utf-8", "ignore") for m in GENAI_MARKERS if m in blob), None)


def dhash(img_bgr: np.ndarray) -> int:
    """64-bit difference hash: survives recompression/resizing, so a re-submitted image is recognised."""
    g = cv2.resize(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def exif_editor(raw: bytes | None) -> str | None:
    """Editing-software tag = weak positive. Missing EXIF is NOT a signal (browsers/WhatsApp strip it)."""
    if not raw:
        return None
    try:
        sw = str(Image.open(io.BytesIO(raw)).getexif().get(305, ""))
    except Exception:
        return None
    return sw if any(t in sw.lower() for t in ("photoshop", "gimp", "canva", "picsart", "snapseed", "pixlr")) else None
