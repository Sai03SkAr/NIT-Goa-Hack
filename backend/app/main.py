"""TrueID Shield API. Run:  cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
Access rules live in app/security.py (deny by default)."""
import hashlib
import io
import json
import pickle
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import networkx as nx
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import db, liveness_sessions, policy
from app.schemas import code_text
from app import security as S
from app.config import (ANALYST_SESSION_TTL_S, APPLY_RATE_PER_MIN, BANDS, CONSENT_VERSION, ENABLE_DEMO_TOOLS, GEN,
                        LIVE_HISTORY, MAX_ACTIVE_JOBS, MAX_FRAMES, MAX_IMAGE_PIXELS, MAX_PAYLOAD_BYTES,
                        MAX_UPLOAD_BYTES, PRE, RETENTION_DAYS, UPLOADS)
from app.graph import pipeline as P
from app.modules.biometric.face import reuse_threshold, threshold
from app.modules.correlation.history import STRONG, History
from app.modules.document import forensics
from app.modules.document.agent import normalize as doc_normalize
from app.modules.registry import mocks


@asynccontextmanager
async def lifespan(_app):
    db.init()
    purge_expired_uploads()
    P.Runtime.bands = dict(BANDS)
    P.Runtime.hist = load_history()
    P.pipeline()
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="TrueID Shield", version="2.0", lifespan=lifespan)
app.include_router(mocks.router)  # /mock/* is analyst-only (deny by default)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204)  # no CORS: the UI is same-origin through the Next.js proxy
    if not S.origin_ok(request):
        return JSONResponse({"detail": "cross-site request refused"}, status_code=403)
    ok, code, why = S.allowed(request)
    if not ok:
        return JSONResponse({"detail": why}, status_code=code)
    path = request.url.path
    if request.method == "POST" and path in ("/api/apply", "/api/auth/login"):
        limit = APPLY_RATE_PER_MIN if path == "/api/apply" else 10
        if not S.rate_ok(path, S.client_ip(request), limit):
            return JSONResponse({"detail": "too many requests from this client, try again in a minute"}, status_code=429)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def purge_expired_uploads() -> int:
    """Retention policy: uploaded card/selfie images older than RETENTION_DAYS are deleted (DB keeps masked fields only)."""
    cutoff, n = time.time() - RETENTION_DAYS * 86400, 0
    for f in UPLOADS.glob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(); n += 1
    return n


# ------------------------------------------------------------------ protected media (analyst only, see security.py)
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _media(base: Path, rel: str):
    target = (base / rel).resolve()
    if not target.is_relative_to(base.resolve()) or target.suffix.lower() not in MEDIA_TYPES or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type=MEDIA_TYPES[target.suffix.lower()], headers={"Cache-Control": "no-store"})


@app.get("/files/{rel:path}")
def files(rel: str):
    return _media(GEN, rel)


@app.get("/uploads/{rel:path}")
def uploads(rel: str):
    return _media(UPLOADS, rel)


def _warm():
    from app.modules.biometric.face import analyzer
    from app.modules.document.ocr import reader
    analyzer(); reader()
    from app.modules.document import trufor
    if trufor.available():
        trufor._model()  # ~8 s; so the first "TruFor" click in a demo is instant


def _live_lines() -> list[dict]:
    """Live history log, tolerant of a torn last line; later duplicates of an app_id are ignored."""
    out, seen = [], set()
    if not LIVE_HISTORY.exists():
        return out
    for line in LIVE_HISTORY.read_text().splitlines():
        try:
            r = json.loads(line)
            aid = r["app"]["app_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if aid not in seen:
            seen.add(aid); out.append(r)
    return out


def load_history() -> History:
    """Replay seeded applications (time order) then live ones so new applicants are linked against them."""
    h = History(reuse_threshold())
    p = GEN / "population.json"
    seen = set()
    if p.exists():
        for a in json.loads(p.read_text()):
            ext = PRE / "extract" / f"{a['app_id']}.pkl"
            emb = media = None
            if ext.exists():
                b = pickle.loads(ext.read_bytes())["bio"]
                emb = b["selfie"]["emb"] if b["selfie"] else None
                media = b["passive"].get("dhash")
            h.add(History.record(a, emb, media)); seen.add(a["app_id"])
    for r in _live_lines():
        if r["app"]["app_id"] not in seen:
            h.add(History.record(r["app"], None if r["emb"] is None else np.asarray(r["emb"], np.float32), r.get("media")))
    return h


# ------------------------------------------------------------------ sessions & sign-in
class Login(BaseModel):
    key: str = Field(max_length=200)


@app.post("/api/auth/login")
def login(body: Login, request: Request):
    if not S.key_ok(body.key):
        raise HTTPException(401, "wrong analyst key")
    token, _ = S.make_token("analyst", ANALYST_SESSION_TTL_S)
    r = JSONResponse({"analyst": True})
    r.set_cookie(S.ANALYST_COOKIE, token, **S.cookie_args(request, ANALYST_SESSION_TTL_S))
    return r


@app.post("/api/auth/logout")
def logout():
    r = JSONResponse({"analyst": False})
    r.delete_cookie(S.ANALYST_COOKIE, path="/")
    return r


@app.get("/api/auth/me")
def me(request: Request):
    return {"analyst": S.is_analyst(request), "demo_tools": ENABLE_DEMO_TOOLS}


@app.post("/api/session")
def applicant_session(request: Request):
    r = JSONResponse({"consent_version": CONSENT_VERSION})
    if not S.applicant_sid(request):
        token, _ = S.make_token("applicant", S.APPLICANT_TTL_S)
        r.set_cookie(S.APPLICANT_COOKIE, token, **S.cookie_args(request, S.APPLICANT_TTL_S))
    return r


@app.post("/api/liveness/challenge")
def liveness_challenge(request: Request):
    return liveness_sessions.issue(S.applicant_sid(request))


# ------------------------------------------------------------------ applicant flow
class FormIn(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=80)
    dob: str = Field(pattern=r"^\d{2}/\d{2}/\d{4}$")
    gender: str = Field(pattern=r"^[MF]$")
    id_number: str = Field(pattern=r"^\d{12}$")
    pan: str = Field(default="", max_length=10)
    phone: str = Field(pattern=r"^\d{10}$")
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    address: str = Field(default="", max_length=200)
    pincode: str = Field(default="", max_length=6)


class DeviceIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    device_id: str | None = Field(default=None, max_length=80)
    user_agent: str = Field(default="", max_length=400)
    camera_labels: list[str] = Field(default_factory=list, max_length=12)
    active_camera: str | None = Field(default=None, max_length=120)


class TelemetryIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fill_time: float | None = None
    iki_mean: float | None = None
    iki_std: float | None = None
    paste_fields: float | None = None
    corrections: float | None = None
    blur_count: float | None = None
    mouse_entropy: float | None = None
    keystroke_vec: list[float] | None = Field(default=None, max_length=32)


class Consent(BaseModel):
    accepted: bool
    version: str


class Geo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float | None = None   # metres
    ts: str | None = None


class ApplyIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    form: FormIn
    device: DeviceIn = Field(default_factory=DeviceIn)
    telemetry: TelemetryIn = Field(default_factory=TelemetryIn)
    consent: Consent
    geo: Geo | None = None           # RBI V-CIP geo-tag; null if the applicant declines location
    challenge_id: str | None = Field(default=None, max_length=64)


class Job:
    def __init__(self, app_id: str, session: str):
        self.app_id, self.session, self.t = app_id, session, time.time()
        self.events: list[dict] = []
        self.done = False


JOBS: dict[str, Job] = {}
IDEMPOTENCY: dict[tuple[str, str], str] = {}
_jobs_lock = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kyc")  # InsightFace/EasyOCR are CPU-bound
JOB_TTL_S = 1800


def _active() -> int:
    return sum(not j.done for j in JOBS.values())


def _sweep_jobs():
    now = time.time()
    for k in [k for k, j in JOBS.items() if j.done and now - j.t > JOB_TTL_S]:
        JOBS.pop(k, None)
    for k in [k for k, v in IDEMPOTENCY.items() if v not in JOBS]:
        IDEMPOTENCY.pop(k, None)


async def _read_image(f: UploadFile, what: str) -> tuple[bytes, np.ndarray]:
    raw = await f.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{what} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return raw, _decode(raw, what)


def _decode(b: bytes, what: str = "image"):
    try:
        with Image.open(io.BytesIO(b)) as im:  # header only: refuse decompression bombs before decoding
            w, h = im.size
            fmt = im.format
    except Exception:
        raise HTTPException(400, f"{what} is not a readable image")
    if fmt not in ("JPEG", "PNG", "WEBP") or w * h > MAX_IMAGE_PIXELS:
        raise HTTPException(400, f"{what}: JPEG/PNG/WebP up to {MAX_IMAGE_PIXELS // 1_000_000} MP only")
    img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, f"{what} is not a readable image")
    return img


def run_job(job: Job, state: dict):
    try:
        for upd in P.pipeline().stream(state, stream_mode="updates"):
            for node, u in upd.items():
                job.events.append(P.jsonable(P.node_event(node, u or {})))
    except Exception as e:  # surface pipeline errors to the progress UI instead of hanging it
        job.events.append({"node": "error", "error": type(e).__name__})
        import traceback; traceback.print_exc()
    job.done, job.t = True, time.time()


@app.post("/api/apply")
async def apply(request: Request, payload: str = Form(..., max_length=MAX_PAYLOAD_BYTES), card: UploadFile = File(...),
                selfie: UploadFile = File(...), frames: list[UploadFile] = File(default=[])):
    """payload JSON: ApplyIn. Liveness frames: [neutral, step1, step2] for the challenge named by challenge_id."""
    sid = S.applicant_sid(request)
    try:
        data = ApplyIn.model_validate_json(payload)
    except ValidationError as e:
        raise HTTPException(422, [{"field": ".".join(map(str, x["loc"])), "msg": x["msg"]} for x in e.errors()][:10])
    if not data.consent.accepted or data.consent.version != CONSENT_VERSION:
        raise HTTPException(422, "consent to the current notice is required")
    idem = (request.headers.get("idempotency-key") or "")[:64]
    with _jobs_lock:
        _sweep_jobs()
        if idem and (sid, idem) in IDEMPOTENCY:
            return {"app_id": IDEMPOTENCY[(sid, idem)], "replayed": True}
        if _active() >= MAX_ACTIVE_JOBS:
            return JSONResponse({"detail": "busy: too many checks running, retry shortly"}, status_code=503,
                                headers={"Retry-After": "10"})
    if len(frames) > MAX_FRAMES:
        raise HTTPException(422, f"at most {MAX_FRAMES} liveness frames")
    card_raw, card_img = await _read_image(card, "card")
    selfie_raw, selfie_img = await _read_image(selfie, "selfie")
    frame_imgs = [(await _read_image(f, "liveness frame"))[1] for f in frames]
    challenge = None
    if data.challenge_id:  # consumed exactly once, even if the frames turn out to be bad
        c, st = liveness_sessions.consume(data.challenge_id, sid)
        challenge = {"status": st, "sequence": c["sequence"] if c else []}

    app_id = "L" + uuid.uuid4().hex[:8].upper()
    (UPLOADS / f"{app_id}_card.jpg").write_bytes(card_raw)
    (UPLOADS / f"{app_id}_selfie.jpg").write_bytes(selfie_raw)
    device = data.device.model_dump() | {"ip": S.signal_ip(request)}  # never the client's claim about its own IP
    geo = data.geo.model_dump() if data.geo else None
    a = {"app_id": app_id, "ts": datetime.now().isoformat(timespec="seconds"), "source": "live",
         "form": data.form.model_dump(), "device": device,
         "telemetry": {k: v for k, v in data.telemetry.model_dump().items() if v is not None},
         "challenge": challenge, "consent": data.consent.model_dump() | {"ts": datetime.now().isoformat(timespec="seconds")}, "geo": geo,
         "card_sha256": hashlib.sha256(card_raw).hexdigest(), "selfie_sha256": hashlib.sha256(selfie_raw).hexdigest(),
         "card_path": f"/uploads/{app_id}_card.jpg", "selfie_path": f"/uploads/{app_id}_selfie.jpg"}
    job = Job(app_id, sid)
    with _jobs_lock:
        JOBS[app_id] = job
        if idem:
            IDEMPOTENCY[(sid, idem)] = app_id
    state = {"app": a, "card_bgr": card_img, "card_raw": card_raw, "selfie_bgr": selfie_img, "selfie_raw": selfie_raw,
             "frames": frame_imgs}
    EXECUTOR.submit(run_job, job, state)
    return {"app_id": app_id}


def _own_job(request: Request, app_id: str) -> Job:
    j = JOBS.get(app_id)
    if j is None or j.session != S.applicant_sid(request):
        raise HTTPException(404, "unknown application")  # same answer for "not yours" and "not there"
    return j


@app.get("/api/apply/{app_id}/events")
def events(app_id: str, request: Request, after: int = 0):
    """Progress by polling (works through any proxy, unlike an event stream)."""
    j = _own_job(request, app_id)
    after = max(0, after)
    return {"events": j.events[after:], "next": len(j.events), "done": j.done}


@app.get("/api/apply/{app_id}/result")
def result(app_id: str, request: Request):
    """What the applicant may see: outcome, which checks are pending, and plain-language reasons. No scores."""
    j = _own_job(request, app_id)
    if not j.done:
        return {"app_id": app_id, "done": False}
    with db.session() as s:
        r = s.get(db.Application, app_id)
    if r is None:
        return {"app_id": app_id, "done": True, "error": True}
    reasons = sorted({x["code"] for m in r.modules for x in m.get("reasons", []) if x.get("weight", 0) > 0})
    return {"app_id": app_id, "done": True, "band": r.band, "reasons": reasons,
            "evidence": [{k: e[k] for k in ("check", "label", "status", "required")} for e in r.evidence]}


# ------------------------------------------------------------------ analyst console
def _row(x: db.Application, full=False) -> dict:
    d = x.model_dump()
    if not full:
        for k in ("modules", "shap", "summary", "form_masked"):
            d.pop(k, None)
    for k in ("card_path", "selfie_path"):
        if d.get(k) and not d[k].startswith("/"):
            d[k] = "/files/" + d[k]
    return P.jsonable(d)


@app.get("/api/apps")
def list_apps(band: str | None = None, ftype: str | None = None, source: str | None = None, q: str | None = None,
              limit: int = 200, offset: int = 0):
    with db.session() as s:
        st = db.select(db.Application).order_by(db.Application.ts.desc())
        if band: st = st.where(db.Application.band == band)
        if ftype: st = st.where(db.Application.fraud_type == ftype)
        if source: st = st.where(db.Application.source == source)
        if q: st = st.where(db.Application.name.contains(q) | db.Application.app_id.contains(q))
        rows = s.exec(st.offset(offset).limit(limit)).all()
        return [_row(r) for r in rows]


@app.get("/api/stats")
def stats():
    with db.session() as s:
        rows = s.exec(db.select(db.Application.band, db.Application.fraud_type, db.Application.source)).all()
    out = {"total": len(rows), "bands": {}, "types": {}, "live": 0}
    for b, t, src in rows:
        out["bands"][b] = out["bands"].get(b, 0) + 1
        out["types"][t] = out["types"].get(t, 0) + 1
        out["live"] += src != "seed"
    return out


@app.get("/api/apps/{app_id}")
def get_app(app_id: str):
    with db.session() as s:
        r = s.get(db.Application, app_id)
        if not r:
            raise HTTPException(404)
        audit = s.exec(db.select(db.AuditLog).where(db.AuditLog.app_id == app_id).order_by(db.AuditLog.ts)).all()
        out = _row(r, full=True)
        out["rule_texts"] = {c: code_text(c) for c in r.rule_codes or []}
        out["audit"] = [P.jsonable(a.model_dump()) for a in audit]
    return out


class Override(BaseModel):
    status: str  # approved | rejected | open
    note: str = Field(default="", max_length=1000)


@app.post("/api/apps/{app_id}/override")
def override(app_id: str, o: Override, request: Request):
    """Analyst disposition. Kept separate from the automated band, which is never edited."""
    if o.status not in ("approved", "rejected", "open"):
        raise HTTPException(422, "bad status")
    with db.session() as s:
        r = s.get(db.Application, app_id)
        if not r:
            raise HTTPException(404)
        against = (o.status == "approved" and r.band != "APPROVE") or (o.status == "rejected" and r.band == "APPROVE")
        if o.status != "open" and len(o.note.strip()) < (20 if against else 5):
            raise HTTPException(422, "write a reason (at least 20 characters when you go against the automated decision)")
        actor, prev = S.analyst_actor(request), r.status
        if o.status == "approved" and r.band == "REJECT":
            # four-eyes rule: approving what the system rejected needs a second analyst (the insider-collusion path).
            # shortcut: analysts are told apart by sign-in session, not named accounts; add real accounts for production.
            asks = s.exec(db.select(db.AuditLog).where(db.AuditLog.app_id == app_id,
                                                        db.AuditLog.action == "override-request:approved")).all()
            if not asks or r.status != "pending_second_approval":
                r.status = "pending_second_approval"
                s.add(r); s.commit()
                db.audit(s, app_id, "override-request:approved", o.note.strip(), actor)
                return {"ok": True, "against_automated": True, "pending_second_approval": True}
            if any(a.actor == actor for a in asks):
                raise HTTPException(409, "a different analyst must confirm this approval")
        r.status = o.status
        s.add(r)
        s.commit()
        flag = " [against automated " + r.band + "]" if against else ""
        db.audit(s, app_id, f"override:{prev}->{o.status}{flag}", o.note.strip(), actor)
    return {"ok": True, "against_automated": against}


@app.get("/api/audit/verify")
def audit_verify():
    return db.verify_audit()


def _card_image(app_id: str):
    with db.session() as s:
        r = s.get(db.Application, app_id)
    if not r:
        raise HTTPException(404)
    path = (UPLOADS.parent / r.card_path.lstrip("/")) if r.card_path.startswith("/uploads") else GEN / r.card_path.removeprefix("/files/")
    img = cv2.imread(str(path))
    if img is None:
        raise HTTPException(404, "card image missing")
    return img


@app.delete("/api/apps/{app_id}")
def erase(app_id: str, request: Request):
    """Right to erasure (DPDP Act 2023): delete the application, its images and its graph record; keep an audit stub."""
    with db.session() as s:
        r = s.get(db.Application, app_id)
        if not r:
            raise HTTPException(404)
        s.delete(r)
        s.commit()
    db.audit(None, app_id, "erased", "applicant data deleted on request", S.analyst_actor(request))
    for f in UPLOADS.glob(f"{app_id}_*"):
        f.unlink()
    with P.Runtime.lock:  # in-memory graph forgets it at the next restart
        keep = [r for r in _live_lines() if r["app"]["app_id"] != app_id]
        LIVE_HISTORY.write_text("".join(json.dumps(r) + "\n" for r in keep))
    return {"erased": app_id}


@app.get("/api/apps/{app_id}/ela.png")
def ela(app_id: str):
    ok, png = cv2.imencode(".png", forensics.ela_heatmap(_card_image(app_id)))
    return Response(png.tobytes(), media_type="image/png")


@app.get("/api/apps/{app_id}/trufor")
def trufor_check(app_id: str):
    """TruFor score + localization heatmap for this card (evidence only, never changes the decision)."""
    from app.modules.document import trufor
    if not trufor.available():
        raise HTTPException(503, "TruFor not installed: run ./scripts/setup_trufor.sh")
    return trufor.analyze(doc_normalize(_card_image(app_id)))


@app.get("/api/graph")
def graph(app_id: str | None = None, hops: int = 2, min_size: int = 3):
    """Strong-edge identity graph. With app_id: its neighbourhood; else all components >= min_size."""
    h = P.Runtime.hist
    G = nx.Graph()
    for a, b, d in h.edges:
        if d["w"] >= STRONG:
            G.add_edge(h.apps[a]["app_id"], h.apps[b]["app_id"], w=d["w"], kinds=list(d["kinds"]))
    if app_id:
        if app_id not in G:
            return {"nodes": [{"id": app_id}], "links": [], "communities": {}}
        G = G.subgraph(nx.ego_graph(G, app_id, radius=hops).nodes)
    else:
        keep = [c for c in nx.connected_components(G) if len(c) >= min_size]
        G = G.subgraph(set().union(*keep) if keep else set())
    comms = nx.community.louvain_communities(G, weight="w", seed=0) if G.number_of_nodes() else []
    cid = {n: i for i, c in enumerate(comms) for n in c}
    # deterministic layout: spring layout per connected component, components packed on a grid (largest first)
    pos = {}
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    cols = max(1, int(np.ceil(np.sqrt(len(comps) * 1.6))))
    for k, comp in enumerate(comps):
        sub = G.subgraph(comp)
        lay = nx.spring_layout(sub, seed=0, k=1.2 / np.sqrt(len(comp))) if len(comp) > 1 else {next(iter(comp)): np.zeros(2)}
        r = 14 + 9 * np.sqrt(len(comp))
        cx, cy = (k % cols) * 130, (k // cols) * 130
        for n, p in lay.items():
            pos[n] = (float(cx + r * p[0]), float(cy + r * p[1]))
    with db.session() as s:
        meta = {r.app_id: r for r in s.exec(db.select(db.Application).where(db.Application.app_id.in_(list(G.nodes)))).all()}
    nodes = [{"id": n, "name": meta[n].name if n in meta else n, "band": meta[n].band if n in meta else None,
              "fraud_type": meta[n].fraud_type if n in meta else None, "source": meta[n].source if n in meta else None,
              "community": cid.get(n), "x": pos[n][0], "y": pos[n][1]} for n in G.nodes]
    links = [{"source": a, "target": b, "w": d["w"], "kinds": d["kinds"]} for a, b, d in G.edges(data=True)]
    return {"nodes": nodes, "links": links, "communities": len(comms)}


# ------------------------------------------------------------------ config, metrics, attack lab
@app.get("/api/config")
def get_config():
    from app.llm.client import provider
    return {"bands": P.Runtime.bands, "face_threshold": threshold(), "llm": provider()}


class Bands(BaseModel):
    approve_below: float
    reject_at: float


@app.post("/api/config/bands")
def set_bands(b: Bands):
    if not 0 < b.approve_below < b.reject_at < 1:
        raise HTTPException(422, "need 0 < approve_below < reject_at < 1")
    P.Runtime.bands = b.model_dump()
    return P.Runtime.bands


def _json(name):
    p = PRE / name
    if not p.exists():
        raise HTTPException(404, f"{name} not computed yet")
    return json.loads(p.read_text())


PUBLIC_METRICS = ("definition", "n_test", "n_fraud", "precision", "recall_fdr", "f1", "fpr", "roc_auc", "pr_auc", "ci95",
                  "ranking_metrics_on", "decision_metrics_on", "held_by_evidence")


@app.get("/api/metrics")
def metrics(request: Request):
    """Analysts get everything; the public landing page gets headline numbers and how they were measured."""
    m = _json("metrics.json")
    man = json.loads((PRE.parent / "models" / "manifest.json").read_text()) if (PRE.parent / "models" / "manifest.json").exists() else {}
    prov = {k: man.get(k) for k in ("policy_version", "feature_schema_version", "git_commit", "evaluation_kind", "split")}
    if not S.is_analyst(request):
        return {"metrics": {k: m[k] for k in PUBLIC_METRICS if k in m}, "provenance": prov}
    return {"metrics": m, "ablation": _json("ablation.json"), "provenance": prov}


@app.get("/api/attacks")
def attacks():
    return _json("attacks.json")


class LiveAttack(BaseModel):
    app_id: str
    attack: str      # jpeg | noise | blur | brightness | recapture | poisson_dob
    level: float = 0


@app.post("/api/attack/live")
def attack_live(req: LiveAttack):
    """Run one attack on one seeded card, live: document module before vs after."""
    import base64
    from PIL import Image
    from app.attacks import FNS
    from app.modules.document import agent as doc
    from app.modules.document.card import poisson_edit
    from app.modules.document.dates import parse
    apps = {a["app_id"]: a for a in json.loads((GEN / "population.json").read_text())}
    a = apps.get(req.app_id)
    if not a:
        raise HTTPException(404, "seeded app not found")
    card = cv2.imread(str(GEN / a["card_path"]))
    form = dict(a["form"])
    if req.attack == "poisson_dob":
        new = (parse(form["dob"]) - timedelta(days=1461)).strftime("%d/%m/%Y")
        pil = Image.fromarray(cv2.cvtColor(doc.normalize(card), cv2.COLOR_BGR2RGB))
        after_img = cv2.cvtColor(np.array(poisson_edit(pil, "dob", new)), cv2.COLOR_RGB2BGR)
        form_after = form | {"dob": new}
    elif req.attack in FNS:
        after_img, form_after = FNS[req.attack](card, req.level), form
    else:
        raise HTTPException(422, "unknown attack")
    today = datetime.fromisoformat(a["ts"]).date()
    before = doc.assess(doc.extract(card), form, today)
    after = doc.assess(doc.extract(after_img), form_after, today)
    jpg = lambda img: "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()).decode()
    from app.modules.document import trufor
    tf = trufor.available()
    pick = lambda r, img: {"risk": r.risk, "reasons": [x.model_dump() for x in r.reasons], "forensic": r.features["doc_forensic"],
                           "qr_valid": r.evidence["qr_signature_valid"], "qr_status": r.evidence.get("qr_status"),
                           "ocr": r.evidence["ocr"], "qr": r.evidence["qr"],
                           "trufor": trufor.analyze(doc.normalize(img)) if tf else None}
    return P.jsonable({"before": pick(before, card) | {"image": jpg(card)}, "after": pick(after, after_img) | {"image": jpg(after_img)},
                       "truth": a["fraud_type"]})


class Ask(BaseModel):
    question: str


@app.post("/api/chat")
def chat(q: Ask):
    from app.llm.investigator import answer
    return P.jsonable(answer(q.question[:1000], P.Runtime.hist))


@app.get("/api/health")
def health():
    from app.fusion import model
    return {"ok": True, "model": "unavailable" if model.load() is None else ("stale" if model.stale() else "ok")}


# ------------------------------------------------------------------ demo: ring simulator + presenter kit
@app.post("/api/ring-sim")
def ring_sim():
    """Inject the 8 pre-built linked applicants through the real pipeline, a minute apart."""
    kit = json.loads((GEN / "ring_sim.json").read_text())
    ids = []
    base = datetime.now()
    tag = uuid.uuid4().hex[:4].upper()
    for j, k in enumerate(kit):
        a = json.loads(json.dumps(k))
        a["app_id"] = f"RS{tag}{j}"
        a["ts"] = (base + timedelta(minutes=j)).isoformat(timespec="seconds")
        a["source"] = "ring_sim"
        a["card_path"], a["selfie_path"] = k["card_path"], k["selfie_path"]
        a.pop("liveness", None)  # injected without a camera: liveness is honestly NOT_PROVIDED
        raw = (GEN / k["card_path"]).read_bytes()
        state = {"app": a, "card_bgr": _decode(raw), "card_raw": raw,
                 "selfie_bgr": cv2.imread(str(GEN / k["selfie_path"])), "frames": []}
        ids.append(a["app_id"])
        run_job(Job(a["app_id"], "ring-sim"), state)  # sequential so each member sees the previous ones
    return {"app_ids": ids}


@app.post("/api/testkit")
def testkit(encrypted: int = 0):
    """Fresh test identities + cards + expected outcomes (see docs/TESTING.md). ?encrypted=N: N genuine people with
    signed and encrypted QR cards instead of the scenario set."""
    from app.testkit import build_testkit
    return build_testkit(P.Runtime.hist, encrypted=max(0, min(encrypted, 20)))


@app.post("/api/demo/kit")
async def demo_kit(photo: UploadFile = File(...)):
    from app.demo_kit import build_kit
    return build_kit((await _read_image(photo, "photo"))[1])
