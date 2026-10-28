"""TruFor (Guillaro et al., CVPR 2023) as on-demand forgery EVIDENCE: a detection score in [0,1] and a localization
heatmap. Not a fusion feature (the model was trained without it), so it never changes a decision; it lets analysts and
judges see what a state-of-the-art pixel detector says next to the signed-QR check.

Setup: ./scripts/setup_trufor.sh (official code + weights into models/trufor/, research-only licence, not committed).
Runs on Apple-silicon GPU (MPS) when available: the backend pins OpenMP to 1 thread, which makes CPU inference slow."""
import hashlib
import sys
from functools import lru_cache

import cv2
import numpy as np

from app.config import GEN, MODELS

ROOT = MODELS / "trufor"
WEIGHTS = ROOT / "weights" / "trufor.pth.tar"
CACHE = GEN / "trufor"


def available() -> bool:
    return WEIGHTS.exists() and (ROOT / "src" / "trufor.yaml").exists()


@lru_cache(maxsize=1)
def _model():
    if not available():
        return None
    import torch
    src = str(ROOT / "src")
    sys.path.insert(0, src)  # their package uses top-level names (config, models); removed right after import
    try:
        from config import _C
        from models.cmx.builder_np_conf import myEncoderDecoder
    finally:
        sys.path.remove(src)
    cfg = _C.clone()
    cfg.defrost()
    cfg.merge_from_file(str(ROOT / "src" / "trufor.yaml"))
    model = myEncoderDecoder(cfg=cfg)
    # official checkpoint, MD5-verified by setup_trufor.sh; it stores a plain dict, so full unpickling is needed
    ckpt = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["state_dict"])
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    return model.to(device).eval(), device


def analyze(img_bgr: np.ndarray) -> dict | None:
    """{'score': detection score, 'heatmap': relative URL of the overlay PNG}. Cached by image content."""
    loaded = _model()
    if loaded is None:
        return None
    key = hashlib.sha1(cv2.imencode(".png", img_bgr)[1].tobytes()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    npz, png = CACHE / f"{key}.npz", CACHE / f"{key}.png"
    if npz.exists() and png.exists():
        return {"score": round(float(np.load(npz)["score"]), 4), "heatmap": f"/files/trufor/{png.name}"}
    score, heat = infer(img_bgr)
    np.savez(npz, score=score)
    cv2.imwrite(str(png), overlay(img_bgr, heat))
    return {"score": round(score, 4), "heatmap": f"/files/trufor/{png.name}"}


def infer(img_bgr: np.ndarray) -> tuple[float, np.ndarray]:
    """Raw TruFor output: detection score and per-pixel manipulation probability (same size as the input)."""
    import torch
    from torch.nn import functional as F
    model, device = _model()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    x = torch.tensor(rgb.transpose(2, 0, 1), dtype=torch.float)[None] / 256.0  # same scaling as their data_core.py
    with torch.no_grad():
        pred, _conf, det, _npp = model(x.to(device))
    return float(torch.sigmoid(det).item()), F.softmax(pred[0], dim=0)[1].cpu().numpy()


def overlay(img_bgr: np.ndarray, heat: np.ndarray) -> np.ndarray:
    h = cv2.resize(heat, (img_bgr.shape[1], img_bgr.shape[0]))
    colored = cv2.applyColorMap((np.clip(h, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)
    return cv2.addWeighted(img_bgr, 0.55, colored, 0.45, 0)


def score(img_bgr) -> float | None:
    r = analyze(img_bgr)
    return None if r is None else r["score"]
