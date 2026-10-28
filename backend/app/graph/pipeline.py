"""LangGraph StateGraph: ingest -> {document, biometric, behavior, registry} in parallel -> correlation -> fusion
-> router (REVIEW & not stepped up -> step_up -> fusion) -> decide -> explain -> persist.
No LLM in the decision path: 'explain' runs after the decision is fixed."""
import json
import math
import operator
import threading
from datetime import datetime
from typing import Annotated, Any, TypedDict

import numpy as np
from langgraph.graph import END, START, StateGraph

from app import db
from app.config import LIVE_HISTORY
from app.fusion import fraud_type, model
from app.llm.summary import summarize
from app.modules.behavior import agent as beh
from app.modules.biometric import agent as bio
from app.modules.correlation import agent as cor
from app.modules.correlation.history import History
from app.modules.document import agent as doc
from app.modules.registry import agent as regm
from app.modules.registry.mocks import registry_face, registry_face_url


class State(TypedDict, total=False):
    app: dict
    card_bgr: Any
    card_raw: bytes
    selfie_bgr: Any
    frames: list
    rec: dict
    modules: Annotated[dict, operator.or_]
    feats: dict
    decision: dict
    stepped_up: bool
    step_up: dict
    summary: str
    summary_source: str
    persisted: bool


class Runtime:
    """Process-wide History + lock (the correlation node is the only writer)."""
    hist: History | None = None
    lock = threading.Lock()
    bands = None


def _today(s):
    return datetime.fromisoformat(s["app"]["ts"]).date()


def ingest(s: State):
    return {"modules": {}, "stepped_up": False}


def document_node(s: State):
    ext = doc.extract(s["card_bgr"], s.get("card_raw"))
    return {"modules": {"document": {**doc.assess(ext, s["app"]["form"], _today(s)).model_dump(), "_ext": ext}}}


def biometric_node(s: State):
    a = s["app"]
    ext = bio.extract(s["selfie_bgr"], doc.normalize(s["card_bgr"]))
    live = dict(a.get("liveness") or {})
    if s.get("frames"):
        chk = bio.verify_frames(s["frames"])
        live["frames_consistent"] = chk["consistent"]
        live["server_check"] = chk
    emb = ext["selfie"]["emb"] if ext["selfie"] else None
    reuse = Runtime.hist.face_matches(emb, a["form"]["name"])
    r = bio.assess(ext, registry_face(a["form"]["id_number"]), live, a["device"].get("camera_labels", []), reuse,
                   registry_face_url(a["form"]["id_number"]), a["device"].get("active_camera"))
    return {"modules": {"biometric": {**r.model_dump(), "_emb": emb}}}


def behavior_node(s: State):
    rec = History.record(s["app"], None)
    return {"modules": {"behavior": beh.assess(s["app"], rec, Runtime.hist).model_dump()}}


def registry_node(s: State):
    return {"modules": {"registry": regm.assess(s["app"]["form"], _today(s)).model_dump()}}


def correlation_node(s: State):
    emb = s["modules"]["biometric"].get("_emb")
    rec = History.record(s["app"], emb)
    with Runtime.lock:
        r = cor.assess(rec, Runtime.hist, commit=True)
        a = s["app"]
        with open(LIVE_HISTORY, "a") as fh:  # the graph is in memory; this log lets a restart rebuild it
            fh.write(json.dumps({"app": {k: a[k] for k in ("app_id", "ts", "form", "device", "telemetry")},
                                 "emb": None if emb is None else [float(x) for x in emb]}) + "\n")
    return {"modules": {"correlation": r.model_dump()}, "rec": {"app_id": rec["app_id"]}}


def fusion_node(s: State):
    feats = {}
    for m in s["modules"].values():
        feats.update(m["features"])
    d = model.decide(feats, Runtime.bands)
    if s.get("stepped_up"):
        v = s["step_up"]["voice"]
        p = min(max(d["prob"], 1e-4), 1 - 1e-4)
        p2 = 1 / (1 + math.exp(-(math.log(p / (1 - p)) + 2.5 * (0.5 - v))))
        d["prob_before_step_up"], d["prob"] = d["prob"], p2
        b = model.band(p2, Runtime.bands)
        d["band"] = d["forced"] if d["forced"] == "REJECT" else b
    return {"feats": feats, "decision": d}


def route(s: State):
    return "step_up" if s["decision"]["band"] == "REVIEW" and not s.get("stepped_up") and not s["decision"]["forced"] else "decide"


def step_up_node(s: State):
    """Real KYC escalates instead of rejecting outright. Voice is SIMULATED (badge in UI)."""
    v = bio.simulated_voice(s["app"]["app_id"], s["feats"].get("bio_sim_registry", float("nan")))
    return {"stepped_up": True, "step_up": {"voice": round(v, 3), "simulated": True, "challenge": "voice_passphrase"}}


def decide_node(s: State):
    ft = fraud_type.classify(s["feats"]) if s["decision"]["band"] != "APPROVE" else "none"
    return {"decision": {**s["decision"], **{f"fraud_{k}": v for k, v in fraud_type.action(ft).items()}}}


def _public_modules(s):
    return [jsonable({k: v for k, v in m.items() if not k.startswith("_")}) for m in s["modules"].values()]


def explain_node(s: State):
    d = s["decision"]
    case = {"band": d["band"], "prob": d["prob"], "fraud_label": d["fraud_label"], "action": d["fraud_action"],
            "modules": _public_modules(s), "shap": d.get("shap", [])}
    text, src = summarize(case)
    return {"summary": text, "summary_source": src}


def persist_node(s: State):
    a, d = s["app"], s["decision"]
    with db.session() as ses:
        ses.merge(db.Application(
            app_id=a["app_id"], ts=a["ts"], source=a.get("source", "live"),
            name=a["form"]["name"], id_last4=a["form"]["id_number"][-4:], form_masked=db.mask_form(a["form"]),
            prob=d["prob"], band=d["band"], forced=d.get("forced"), rule_codes=d.get("rule_codes", []),
            fraud_type=d["fraud_type"], fraud_label=d["fraud_label"], action=d["fraud_action"],
            modules=_public_modules(s), shap=d.get("shap", []), summary=s.get("summary", ""),
            stepped_up=bool(s.get("stepped_up")), card_path=a.get("card_path", ""), selfie_path=a.get("selfie_path", ""),
            truth_label=a.get("label"), truth_type=a.get("fraud_type")))
        db.audit(ses, a["app_id"], f"decision:{d['band']}", f"p={d['prob']:.3f} type={d['fraud_type']}")
        ses.commit()
    return {"persisted": True}


def build():
    g = StateGraph(State)
    for name, fn in [("ingest", ingest), ("document", document_node), ("biometric", biometric_node),
                     ("behavior", behavior_node), ("registry", registry_node), ("correlation", correlation_node),
                     ("fusion", fusion_node), ("step_up", step_up_node), ("decide", decide_node),
                     ("explain", explain_node), ("persist", persist_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "ingest")
    for n in ("document", "biometric", "behavior", "registry"):
        g.add_edge("ingest", n)
    g.add_edge(["document", "biometric", "behavior", "registry"], "correlation")
    g.add_edge("correlation", "fusion")
    g.add_conditional_edges("fusion", route, {"step_up": "step_up", "decide": "decide"})
    g.add_edge("step_up", "fusion")
    g.add_edge("decide", "explain")
    g.add_edge("explain", "persist")
    g.add_edge("persist", END)
    return g.compile()


PIPELINE = None


def pipeline():
    global PIPELINE
    if PIPELINE is None:
        PIPELINE = build()
    return PIPELINE


def node_event(node: str, update: dict) -> dict:
    """Small JSON-safe event for the live progress UI."""
    ev = {"node": node}
    for m in (update.get("modules") or {}).values():
        ev.update({"module": m["module"], "risk": m["risk"], "reasons": [r["code"] for r in m["reasons"]],
                   "latency_ms": m["latency_ms"], "simulated": m.get("simulated", False)})
    if "decision" in update:
        d = update["decision"]
        ev.update({k: d.get(k) for k in ("prob", "band", "forced", "fraud_label", "fraud_action") if k in d})
    if "step_up" in update:
        ev["step_up"] = update["step_up"]
    if "summary" in update:
        ev["summary"] = update["summary"]
    return ev


def jsonable(x):
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if (isinstance(x, float) or isinstance(x, np.floating)) and math.isnan(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.ndarray):
        return None
    return x
