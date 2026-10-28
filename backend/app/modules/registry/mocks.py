"""Five mock external registries (UIDAI-like, PAN, telecom, CKYC, credit bureau), each its own FastAPI router
so the demo shows real 'external lookups'. Data comes from data/generated/registry.json."""
import json
from functools import lru_cache

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException

from app.config import GEN, PRE

router = APIRouter(prefix="/mock", tags=["mock registries"])


@lru_cache(maxsize=1)
def db() -> dict:
    p = GEN / "registry.json"
    return json.loads(p.read_text()) if p.exists() else {"uidai": {}, "pan": {}, "telecom": {}, "ckyc": {}, "bureau": {}}


_face_cache: dict[str, np.ndarray] = {}


@lru_cache(maxsize=1)
def _precomputed_faces() -> dict:
    p = PRE / "registry_emb.npz"
    return dict(np.load(p)) if p.exists() else {}


def registry_face(id_number: str):
    """Face embedding the issuer holds for this ID (precomputed, else computed once and cached)."""
    rec = db()["uidai"].get(id_number)
    if not rec:
        return None
    pre = _precomputed_faces()
    if id_number in pre:
        return pre[id_number]
    if id_number not in _face_cache:
        from app.modules.biometric.face import embed
        e = embed(cv2.imread(str(GEN / rec["face"])))
        _face_cache[id_number] = None if e is None else e["emb"]
    return _face_cache[id_number]


def registry_face_url(id_number: str) -> str | None:
    rec = db()["uidai"].get(id_number)
    return f"/files/{rec['face']}" if rec else None


def uidai(id_number: str):
    r = db()["uidai"].get(id_number)
    return None if r is None else {k: v for k, v in r.items() if k != "face"}


def pan(p: str):
    return db()["pan"].get((p or "").upper())


def telecom(phone: str):
    return db()["telecom"].get(phone)


def ckyc(id_number: str):
    return db()["ckyc"].get(id_number)


def bureau(id_number: str):
    return db()["bureau"].get(id_number)


def _or404(x):
    if x is None:
        raise HTTPException(404, "not found")
    return x


@router.get("/uidai/{id_number}")
def r_uidai(id_number: str):
    return _or404(uidai(id_number))


@router.get("/pan/{p}")
def r_pan(p: str):
    return _or404(pan(p))


@router.get("/telecom/{phone}")
def r_telecom(phone: str):
    return _or404(telecom(phone))


@router.get("/ckyc/{id_number}")
def r_ckyc(id_number: str):
    return _or404(ckyc(id_number))


@router.get("/bureau/{id_number}")
def r_bureau(id_number: str):
    return _or404(bureau(id_number))
