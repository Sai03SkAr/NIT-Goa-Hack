"""TruFor adapter. Returns None until weights + repo are set up (plan 4.1 fallback: semantic + crypto checks carry D2)."""
from functools import lru_cache

from app.config import MODELS


@lru_cache(maxsize=1)
def _model():
    if not (MODELS / "trufor" / "weights" / "trufor.pth.tar").exists():
        return None
    return None  # wired in by eval/setup_trufor.py once weights are downloaded


def score(card_bgr) -> float | None:
    m = _model()
    return None if m is None else float(m(card_bgr))
