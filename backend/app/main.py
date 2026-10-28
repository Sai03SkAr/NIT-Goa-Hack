"""TrueID Shield API. Run:  cd backend && ../.venv/bin/uvicorn app.main:app --port 8000"""
import asyncio
import json
import pickle
import queue
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import cv2
import networkx as nx
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app import db
from app.config import BANDS, GEN, LIVE_HISTORY, PRE, UPLOADS
from app.graph import pipeline as P
from app.modules.biometric.face import reuse_threshold, threshold
from app.modules.correlation.history import STRONG, History
from app.modules.document import forensics
from app.modules.registry import mocks

@asynccontextmanager
async def lifespan(_app):
    db.init()
    P.Runtime.bands = dict(BANDS)
    P.Runtime.hist = load_history()
    P.pipeline()
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="TrueID Shield", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(mocks.router)
app.mount("/files", StaticFiles(directory=GEN), name="files")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")

JOBS: dict[str, queue.Queue] = {}


def _warm():
    from app.modules.biometric.face import analyzer
    from app.modules.document.ocr import reader
    analyzer(); reader()


def load_history() -> History:
    """Replay seeded applications (time order) so live applicants are linked against them."""
    h = History(reuse_threshold())
    p = GEN / "population.json"
    if not p.exists():
        return h
    for a in json.loads(p.read_text()):
        ext = PRE / "extract" / f"{a['app_id']}.pkl"
        emb = None
        if ext.exists():
            s = pickle.loads(ext.read_bytes())["bio"]["selfie"]
            emb = s["emb"] if s else None
        h.add(History.record(a, emb))
    if LIVE_HISTORY.exists():
        for line in LIVE_HISTORY.read_text().splitlines():
            r = json.loads(line)
            h.add(History.record(r["app"], None if r["emb"] is None else np.asarray(r["emb"], np.float32)))
    return h


# ------------------------------------------------------------------ applicant flow
def _decode(b: bytes):
    img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "unreadable image")
    return img


def run_job(app_id: str, state: dict):
    q = JOBS[app_id]
    try:
        for upd in P.pipeline().stream(state, stream_mode="updates"):
            for node, u in upd.items():
                q.put(P.jsonable(P.node_event(node, u or {})))
    except Exception as e:  # surface pipeline errors to the progress UI instead of hanging it
        q.put({"node": "error", "error": str(e)})
    q.put(None)


@app.post("/api/apply")
async def apply(payload: str = Form(...), card: UploadFile = File(...), selfie: UploadFile = File(...),
                frames: list[UploadFile] = File(default=[])):
    """payload JSON: {form:{...}, device:{device_id, ip?, user_agent, camera_labels[]}, telemetry:{...},
    liveness:{challenges[], passed, virtual_camera}}"""
    data = json.loads(payload)
    for k in ("name", "dob", "gender", "id_number", "phone", "email"):
        if not data.get("form", {}).get(k):
            raise HTTPException(422, f"form.{k} required")
    app_id = "L" + uuid.uuid4().hex[:8].upper()
    card_raw, selfie_raw = await card.read(), await selfie.read()
    (UPLOADS / f"{app_id}_card.jpg").write_bytes(card_raw)
    (UPLOADS / f"{app_id}_selfie.jpg").write_bytes(selfie_raw)
    frame_imgs = [_decode(await f.read()) for f in frames]
    tele = {"field_times": [], "fill_time": 60, "iki_mean": 180, "iki_std": 60, "paste_fields": 0, "corrections": 2,
            "blur_count": 0, "mouse_entropy": 3.0, "keystroke_vec": [0.0] * 12} | data.get("telemetry", {})
    a = {"app_id": app_id, "ts": datetime.now().isoformat(timespec="seconds"), "source": data.get("source", "live"),
         "form": data["form"], "device": {"ip": "127.0.0.1"} | data.get("device", {}), "telemetry": tele,
         "liveness": data.get("liveness", {"passed": False}),
         "card_path": f"/uploads/{app_id}_card.jpg", "selfie_path": f"/uploads/{app_id}_selfie.jpg"}
    JOBS[app_id] = queue.Queue()
    state = {"app": a, "card_bgr": _decode(card_raw), "card_raw": card_raw, "selfie_bgr": _decode(selfie_raw),
             "frames": frame_imgs}
    threading.Thread(target=run_job, args=(app_id, state), daemon=True).start()
    return {"app_id": app_id}


@app.get("/api/apply/{app_id}/events")
async def events(app_id: str):
    q = JOBS.get(app_id)
    if q is None:
        raise HTTPException(404, "unknown job")

    async def gen():
        while True:
            ev = await asyncio.to_thread(q.get)
            if ev is None:
                yield {"event": "done", "data": json.dumps({"app_id": app_id})}
                JOBS.pop(app_id, None)
                return
            yield {"event": "node", "data": json.dumps(ev)}
    return EventSourceResponse(gen())


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
        out["audit"] = [P.jsonable(a.model_dump()) for a in audit]
    return out


class Override(BaseModel):
    status: str  # approved | rejected | open
    note: str = ""
    actor: str = "analyst"


@app.post("/api/apps/{app_id}/override")
def override(app_id: str, o: Override):
    if o.status not in ("approved", "rejected", "open"):
        raise HTTPException(422, "bad status")
    with db.session() as s:
        r = s.get(db.Application, app_id)
        if not r:
            raise HTTPException(404)
        r.status = o.status
        s.add(r)
        db.audit(s, app_id, f"override:{o.status}", o.note, o.actor)
        s.commit()
    return {"ok": True}


@app.get("/api/apps/{app_id}/ela.png")
def ela(app_id: str):
    with db.session() as s:
        r = s.get(db.Application, app_id)
    if not r:
        raise HTTPException(404)
    path = (UPLOADS.parent / r.card_path.lstrip("/")) if r.card_path.startswith("/uploads") else GEN / r.card_path
    img = cv2.imread(str(path))
    ok, png = cv2.imencode(".png", forensics.ela_heatmap(img))
    return Response(png.tobytes(), media_type="image/png")


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
    return {"bands": P.Runtime.bands, "face_threshold": threshold(), "llm": bool(__import__("os").getenv("GEMINI_API_KEY"))}


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


@app.get("/api/metrics")
def metrics():
    return {"metrics": _json("metrics.json"), "ablation": _json("ablation.json")}


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
    ok, enc = cv2.imencode(".jpg", after_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    pick = lambda r: {"risk": r.risk, "reasons": [x.code for x in r.reasons], "forensic": r.features["doc_forensic"],
                      "qr_valid": r.evidence["qr_signature_valid"], "ocr": r.evidence["ocr"], "qr": r.evidence["qr"]}
    return P.jsonable({"before": pick(before), "after": pick(after), "truth": a["fraud_type"],
                       "image": "data:image/jpeg;base64," + base64.b64encode(enc.tobytes()).decode()})


class Ask(BaseModel):
    question: str


@app.post("/api/chat")
def chat(q: Ask):
    from app.llm.investigator import answer
    return P.jsonable(answer(q.question[:1000], P.Runtime.hist))


@app.get("/api/health")
def health():
    return {"ok": True, "history": len(P.Runtime.hist.apps) if P.Runtime.hist else 0}


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
        raw = (GEN / k["card_path"]).read_bytes()
        state = {"app": a, "card_bgr": _decode(raw), "card_raw": raw,
                 "selfie_bgr": cv2.imread(str(GEN / k["selfie_path"])), "frames": []}
        JOBS[a["app_id"]] = queue.Queue()
        ids.append(a["app_id"])
        run_job(a["app_id"], state)  # sequential so each member sees the previous ones
        JOBS.pop(a["app_id"], None)
    return {"app_ids": ids}


@app.post("/api/demo/kit")
async def demo_kit(photo: UploadFile = File(...)):
    from app.demo_kit import build_kit
    return build_kit(_decode(await photo.read()))
