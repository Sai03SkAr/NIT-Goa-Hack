"""Image perturbations shared by the Attack Lab precompute (eval/run_attacks.py) and the live attack endpoint."""
import cv2
import numpy as np


def jpeg(img, q):
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(q)])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def noise(img, s):
    return np.clip(img + np.random.default_rng(0).normal(0, s, img.shape), 0, 255).astype(np.uint8)


def blur(img, s):
    return img if s == 0 else cv2.GaussianBlur(img, (0, 0), s)


def brightness(img, a):
    return np.clip(img.astype(np.float32) * a + (1 - a) * 40, 0, 255).astype(np.uint8)


def recapture(img, s):
    """Screen recapture: perspective tilt + moire + blur."""
    if s == 0:
        return img
    h, w = img.shape[:2]
    d = 0.06 * s
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[w * d, h * d * .5], [w * (1 - d * .3), 0], [w, h], [0, h * (1 - d * .4)]])
    out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REPLICATE)
    yy, xx = np.mgrid[:h, :w]
    out = np.clip(out + (10 * s * np.sin(xx * .8 + yy * .3))[..., None], 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(out, (0, 0), 0.8 * s)


FNS = {"jpeg": jpeg, "noise": noise, "blur": blur, "brightness": brightness, "recapture": recapture}
