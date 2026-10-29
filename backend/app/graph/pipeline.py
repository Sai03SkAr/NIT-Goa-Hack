"""LangGraph StateGraph: ingest -> {document, biometric, behavior, registry} in parallel -> correlation -> fusion
-> router (REVIEW -> step_up, display only) -> decide -> explain -> persist.
The band comes from app/policy.py alone. The simulated voice step-up is shown to the analyst but never changes it,
and no LLM is in the decision path: 'explain' runs after the decision is fixed."""
import json
import math
import operator
import threading
from datetime import datetime
from typing import Annotated, Any, TypedDict

import numpy as np
from langgraph.graph import END, START, StateGraph

from app import consortium, db, policy
from app.config import LIVE_HISTORY
from app.fusion import fraud_type, model
from app.llm.summary import summarize
from app.modules.behavior import agent as beh
from app.modules.biometric import agent as bio
from app.modules.correlation import agent as cor
from app.modules.correlation.history import History
from app.modules.document import agent as doc
from app.modules.registry import agent as regm
from app.modules.registry.mocks import RegistryUnavailable, registry_face, registry_face_url


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
    ext = bio.extract(s["selfie_bgr"], doc.normalize(s["card_bgr"]), s.get("selfie_raw"))
    emb = ext["selfie"]["emb"] if ext["selfie"] else None
    media = ext["passive"]["dhash"]
    ch = a.get("challenge") or {}
    if not ch:
        live = bio.not_provided("upload" if not s.get("frames") else "no_challenge")
    elif ch.get("status") != "VALID":
        live = bio.challenge_rejected(ch.get("status", "UNKNOWN"))
    else:
        live = bio.verify_challenge(s.get("frames") or [], ch["sequence"], emb)
    try:
        reg_emb, reg_url, reg_ok = registry_face(a["form"]["id_number"]), registry_face_url(a["form"]["id_number"]), True
    except RegistryUnavailable:
        reg_emb, reg_url, reg_ok = None, None, False
    with Runtime.lock:
        reuse = Runtime.hist.face_matches(emb, a["form"]["name"]) | {"media": Runtime.hist.media_matches(media)}
    r = bio.assess(ext, reg_emb, live, a["device"].get("camera_labels", []), reuse, reg_url,
                   a["device"].get("active_camera"), registry_available=reg_ok)
    return {"modules": {"biometric": {**r.model_dump(), "_emb": emb, "_media": media}}}


def behavior_node(s: State):
    rec = History.record(s["app"], None)
    with Runtime.lock:
        r = beh.assess(s["app"], rec, Runtime.hist)
    return {"modules": {"behavior": r.model_dump()}}


def registry_node(s: State):
    return {"modules": {"registry": regm.assess(s["app"]["form"], _today(s)).model_dump()}}


def correlation_node(s: State):
    emb = s["modules"]["biometric"].get("_emb")
    rec = History.record(s["app"], emb, s["modules"]["biometric"].get("_media"))
    with Runtime.lock:
        r = cor.assess(rec, Runtime.hist, commit=True)
    return {"modules": {"correlation": r.model_dump()}, "rec": {"app_id": rec["app_id"]}}


def network_module(app: dict) -> dict:
    """Cross-institution check (app/consortium.py): hashed identifiers matched against OTHER institutions."""
    from app.schemas import ModuleResult, reason
    t0 = datetime.now()
    try:
        toks, name_tok = consortium.tokens_for(app)
        r = consortium.check(consortium.institution_of(app), toks, name_tok)
    except Exception:  # noqa: BLE001  the network being down never blocks or passes a case
        r = {"status": policy.UNAVAILABLE, "alerts": [], "seen_elsewhere": {}}
    reasons = [reason(a["code"], 0.3) for a in {a["code"]: a for a in r["alerts"]}.values()]
    return ModuleResult(module="network", risk=round(min(1.0, 0.45 * len(reasons)), 3), reasons=reasons,
                        features={"ev_network": policy.CODE[r["status"]]},
                        latency_ms=int((datetime.now() - t0).total_seconds() * 1000),
                        evidence={"alerts": r["alerts"], "seen_at_other_institutions": r["seen_elsewhere"]}).model_dump()


def fusion_node(s: State):
    feats = {}
    for m in s["modules"].values():
        feats.update(m["features"])
    net = network_module(s["app"])
    feats.update(net["features"])
    return {"feats": feats, "decision": model.decide(feats, Runtime.bands), "modules": {"network": net}}


def route(s: State):
    return "step_up" if s["decision"]["band"] == "REVIEW" else "decide"


def step_up_node(s: State):
    """Real KYC escalates instead of rejecting outright. Voice is SIMULATED: shown to the analyst, never scored."""
    v = bio.simulated_voice(s["app"]["app_id"], s["feats"].get("bio_sim_registry", float("nan")))
    return {"stepped_up": True, "step_up": {"voice": round(v, 3), "simulated": True, "challenge": "voice_passphrase",
                                            "affects_decision": False}}


def decide_node(s: State):
    ft = fraud_type.classify(s["feats"]) if s["decision"]["band"] != "APPROVE" else "none"
    return {"decision": {**s["decision"], **{f"fraud_{k}": v for k, v in fraud_type.action(ft).items()}}}


def _public_modules(s):
    return [jsonable({k: v for k, v in m.items() if not k.startswith("_")}) for m in s["modules"].values()]


def explain_node(s: State):
    d = s["decision"]
    case = {"band": d["band"], "prob": d["prob"], "fraud_label": d["fraud_label"], "action": d["fraud_action"],
            "modules": _public_modules(s), "shap": d.get("shap", []),
            "rule_codes_ev": [c for c in d.get("rule_codes", []) if c.startswith("EV_") or c == "MODEL_UNAVAILABLE"]}
    text, src = summarize(case)
    return {"summary": text, "summary_source": src}


def persist_node(s: State):
    a, d = s["app"], s["decision"]
    emb = s["modules"]["biometric"].get("_emb")
    with Runtime.lock, open(LIVE_HISTORY, "a") as fh:  # written once the case is final; a restart replays it
        fh.write(json.dumps({"app": {k: a[k] for k in ("app_id", "ts", "form", "device", "telemetry")},
                             "emb": None if emb is None else [float(x) for x in emb],
                             "media": s["modules"]["biometric"].get("_media")}) + "\n")
    with db.session() as ses:
        ctx = {"geo": a.get("geo"), "ip": a.get("device", {}).get("ip"), "consent": a.get("consent"),
               "ts": a.get("ts")}
        feats_ev = {**s["feats"], **policy.context_codes(a)}
        ses.merge(db.Application(
            app_id=a["app_id"], ts=a["ts"], source=a.get("source", "live"),
            name=a["form"]["name"], id_last4=a["form"]["id_number"][-4:], form_masked=db.mask_form(a["form"]),
            prob=d["prob"], band=d["band"], forced=d.get("forced"), rule_codes=d.get("rule_codes", []),
            evidence=policy.evidence_list(feats_ev), model_status=d.get("model_status", ""),
            policy_version=d.get("policy_version", ""), step_up=s.get("step_up") or {}, context=ctx,
            fraud_type=d["fraud_type"], fraud_label=d["fraud_label"], action=d["fraud_action"],
            modules=_public_modules(s), shap=d.get("shap", []), summary=s.get("summary", ""),
            stepped_up=bool(s.get("stepped_up")), card_path=a.get("card_path", ""), selfie_path=a.get("selfie_path", ""),
            truth_label=a.get("label"), truth_type=a.get("fraud_type")))
        p = "model unavailable" if d["prob"] is None else f"p={d['prob']:.3f}"
        db.audit(ses, a["app_id"], f"decision:{d['band']}", f"{p} type={d['fraud_type']} {d['policy_version']}")
        ses.commit()
    try:  # share this case's hashed identifiers and outcome with the consortium (no PII leaves in the store)
        toks, name_tok = consortium.tokens_for(a)
        consortium.record(consortium.institution_of(a), toks, name_tok, outcome=d["band"], ref=a["app_id"])
    except Exception:  # noqa: BLE001
        pass
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
    g.add_edge("step_up", "decide")
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
                   "reason_texts": {r["code"]: r["text"] for r in m["reasons"]},
                   "latency_ms": m["latency_ms"], "simulated": m.get("simulated", False)})
    if "decision" in update:
        d = update["decision"]
        ev.update({k: d.get(k) for k in ("prob", "band", "forced", "rule_codes", "fraud_label", "fraud_action",
                                          "approval_eligible", "unresolved", "model_status") if k in d})
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
