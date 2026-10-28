import json
from functools import lru_cache

import cv2
import numpy as np

from app.config import DEFAULT_FACE_THRESHOLD, FACE_THRESHOLD_FILE
from app.modules.document import card as C


@lru_cache(maxsize=1)
def analyzer():
    from insightface.app import FaceAnalysis
    fa = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"],
                      allowed_modules=["detection", "recognition", "landmark_3d_68"])
    fa.prepare(ctx_id=-1, det_size=(480, 480))
    return fa


@lru_cache(maxsize=1)
def threshold() -> float:
    if FACE_THRESHOLD_FILE.exists():
        return float(json.loads(FACE_THRESHOLD_FILE.read_text())["threshold"])
    return DEFAULT_FACE_THRESHOLD


@lru_cache(maxsize=1)
def reuse_threshold() -> float:
    """Stricter threshold for 1:N face-reuse search (FAR ~1e-4 per comparison)."""
    if FACE_THRESHOLD_FILE.exists():
        return float(json.loads(FACE_THRESHOLD_FILE.read_text()).get("reuse_threshold", 0.45))
    return 0.45


def embed(img_bgr: np.ndarray) -> dict | None:
    """Largest face: normed 512-d embedding + head pose (pitch, yaw, roll)."""
    img = img_bgr
    if max(img.shape[:2]) < 320:  # small crops detect better upscaled
        s = 320 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=s, fy=s)
    faces = analyzer().get(img)
    if not faces:
        return None
    f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    pose = getattr(f, "pose", None)
    return {"emb": f.normed_embedding.astype(np.float32), "pose": None if pose is None else [float(p) for p in pose],
            "det": float(f.det_score)}


def card_portrait(card_norm_bgr: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = C.PORTRAIT
    return card_norm_bgr[max(0, y0 - 10):y1 + 10, max(0, x0 - 10):x1 + 10]


def sim(a, b) -> float:
    if a is None or b is None:
        return float("nan")
    return float(np.dot(a, b))


def passive(selfie_bgr: np.ndarray) -> dict:
    g = cv2.cvtColor(selfie_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = float(cv2.Laplacian(g, cv2.CV_32F).var())
    F = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean())))
    h, w = F.shape
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot(yy - h / 2, xx - w / 2)
    band = F[(r > min(h, w) * .15) & (r < min(h, w) * .45)]
    moire = float(band.max() / (np.median(band) + 1e-6))  # isolated strong peak = periodic screen pattern
    return {"blur": round(blur, 1), "moire": round(moire, 1)}
