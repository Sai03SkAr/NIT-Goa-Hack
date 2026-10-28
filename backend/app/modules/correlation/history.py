"""In-memory, append-only index of prior applications. Every query is 'as of now': only apps already added
are visible, so batch training never sees the future. Also builds the weighted identity graph (plan 4.5)."""
import hashlib
import hmac
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np

from app.config import EDGE_BASE, HMAC_KEY, PLACEHOLDERS
from app.modules.correlation.fuzzy import email_stem, name_sim

STRONG = 0.45      # edge weight that joins two applications into one component
KS_LINK = 0.90     # keystroke-vector cosine for a rhythm link
FACE_LINK = None   # set from face threshold at runtime


def id_hash(idn: str) -> str:
    return hmac.new(HMAC_KEY, (idn or "").encode(), hashlib.sha256).hexdigest()[:16]


def clean(v: str | None) -> str | None:
    v = (v or "").strip().lower()
    return None if v in PLACEHOLDERS else v


class History:
    def __init__(self, face_threshold: float):
        self.face_thr = face_threshold
        self.apps: list[dict] = []
        self.idx: dict[str, int] = {}
        self.by_attr: dict[tuple, list[int]] = defaultdict(list)
        self.faces: list[np.ndarray] = []
        self.face_owner: list[int] = []
        self.ks: list[np.ndarray] = []
        self.ks_owner: list[int] = []
        self.stems: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.parent: list[int] = []
        self.members: dict[int, list[int]] = {}
        self.edges: list[tuple[int, int, dict]] = []
        self.media: list[int] = []
        self.media_owner: list[int] = []

    # ------------------------------------------------------------ record
    @staticmethod
    def record(app: dict, face_emb, media: int | None = None) -> dict:
        f, d = app["form"], app["device"]
        stem, num = email_stem(f.get("email", ""))
        return {"app_id": app["app_id"], "ts": datetime.fromisoformat(app["ts"]) if isinstance(app["ts"], str) else app["ts"],
                "name": f["name"], "surname": f["name"].split()[-1].upper(),
                "attrs": {"id_hash": id_hash(f["id_number"]), "device": clean(d.get("device_id")),
                          "phone": clean(f.get("phone")), "address": clean(f"{f.get('address', '')}|{f.get('pincode', '')}"),
                          "ip": clean(d.get("ip"))},
                "stem": stem if num is not None and len(stem) >= 3 else None, "num": num,
                "face": None if face_emb is None else np.asarray(face_emb, np.float32), "media": media,
                "ks": np.asarray((app.get("telemetry") or {}).get("keystroke_vec") or [0.0] * 12, np.float32)}  # zeros never link

    def _find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def _union(self, a, b):
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return
        if len(self.members[ra]) < len(self.members[rb]):
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.members[ra] += self.members.pop(rb)

    # ------------------------------------------------------------ queries (as of now)
    def count_window(self, attr, value, ts, window: timedelta) -> int:
        if value is None:
            return 0
        return sum(1 for i in self.by_attr.get((attr, value), []) if ts - window <= self.apps[i]["ts"] <= ts)

    def shared_names(self, attr, value, name) -> int:
        if value is None:
            return 0
        names = {self.apps[i]["name"] for i in self.by_attr.get((attr, value), [])}
        return sum(1 for n in names if name_sim(n, name) < 0.8)

    def face_matches(self, emb, name) -> dict:
        if emb is None or not self.faces:
            return {"diff_name": 0, "same_name": 0, "max_sim": 0.0, "matches": []}
        sims = np.stack(self.faces) @ emb
        hit = np.where(sims > self.face_thr)[0]
        diff = [self.face_owner[k] for k in hit if name_sim(self.apps[self.face_owner[k]]["name"], name) < 0.8]
        same = len(hit) - len(diff)
        return {"diff_name": len(diff), "same_name": same, "max_sim": float(sims.max()),
                "matches": [self.apps[i]["app_id"] for i in diff[:10]]}

    def media_matches(self, h: int | None, max_bits: int = 6) -> int:
        """Earlier applications whose selfie is the same picture (Hamming distance of 64-bit dHash)."""
        if h is None or not self.media:
            return 0
        x = np.array(self.media, dtype=np.uint64) ^ np.uint64(h)
        return int((np.bitwise_count(x) <= max_bits).sum())

    def device_people(self, device, ts, name, window: timedelta = timedelta(days=7)) -> int:
        """Different people (name and surname both differ) onboarded from this device in the window: a handler
        bringing real account holders (mule herding). Same-surname households are left out."""
        if device is None:
            return 0
        sur = name.split()[-1].upper() if name else ""
        people = {self.apps[i]["name"] for i in self.by_attr.get(("device", device), [])
                  if ts - window <= self.apps[i]["ts"] <= ts}
        return sum(1 for n in people if name_sim(n, name) < 0.8 and n.split()[-1].upper() != sur)

    def keystroke_matches(self, vec, name) -> dict:
        if not self.ks:
            return {"links": 0, "max_sim": 0.0, "matches": []}
        M = np.stack(self.ks)
        sims = (M @ vec) / (np.linalg.norm(M, axis=1) * np.linalg.norm(vec) + 1e-9)
        hit = [self.ks_owner[k] for k in np.where(sims > KS_LINK)[0]
               if name_sim(self.apps[self.ks_owner[k]]["name"], name) < 0.8]
        return {"links": len(hit), "max_sim": float(sims.max()), "matches": [self.apps[i]["app_id"] for i in hit[:10]]}

    def email_sequence(self, stem, num, name) -> int:
        if stem is None:
            return 0
        return sum(1 for i, n in self.stems.get(stem, []) if abs(n - num) <= 5 and name_sim(self.apps[i]["name"], name) < 0.8)

    def specificity(self, count: int) -> float:
        n = max(len(self.apps), 2)
        return math.log(1 + n / max(count, 1)) / math.log(1 + n)

    def link(self, rec: dict) -> dict[int, dict]:
        """Weighted edges from a new record to prior apps (noisy-or over shared attributes)."""
        e: dict[int, dict] = defaultdict(dict)
        for attr, val in rec["attrs"].items():
            if val is None:
                continue
            prior = self.by_attr.get((attr, val), [])
            if prior:
                w = EDGE_BASE[attr] * self.specificity(len(prior) + 1)
                for i in prior:
                    e[i][attr] = w
        if rec["stem"]:
            for i, n in self.stems.get(rec["stem"], []):
                if abs(n - rec["num"]) <= 5:
                    e[i]["email_stem"] = EDGE_BASE["email_stem"]
        if rec["face"] is not None and self.faces:
            sims = np.stack(self.faces) @ rec["face"]
            for k in np.where(sims > self.face_thr)[0]:
                e[self.face_owner[k]]["face"] = EDGE_BASE["face"]
        if self.ks:
            M = np.stack(self.ks)
            sims = (M @ rec["ks"]) / (np.linalg.norm(M, axis=1) * np.linalg.norm(rec["ks"]) + 1e-9)
            for k in np.where(sims > KS_LINK)[0]:
                e[self.ks_owner[k]]["keystroke"] = EDGE_BASE["keystroke"]
        return e

    @staticmethod
    def edge_weight(kinds: dict) -> float:
        p = 1.0
        for w in kinds.values():
            p *= 1 - min(w, 0.99)
        return 1 - p

    # ------------------------------------------------------------ add
    def add(self, rec: dict, edges: dict[int, dict] | None = None) -> int:
        edges = self.link(rec) if edges is None else edges
        i = len(self.apps)
        self.apps.append(rec)
        self.idx[rec["app_id"]] = i
        self.parent.append(i)
        self.members[i] = [i]
        for attr, val in rec["attrs"].items():
            if val is not None:
                self.by_attr[(attr, val)].append(i)
        if rec["face"] is not None:
            self.faces.append(rec["face"]); self.face_owner.append(i)
        self.ks.append(rec["ks"]); self.ks_owner.append(i)
        if rec.get("media") is not None:
            self.media.append(int(rec["media"])); self.media_owner.append(i)
        if rec["stem"]:
            self.stems[rec["stem"]].append((i, rec["num"]))
        for j, kinds in edges.items():
            w = self.edge_weight(kinds)
            self.edges.append((j, i, {"kinds": kinds, "w": round(w, 3)}))
            if w >= STRONG:
                self._union(i, j)
        return i

    def component(self, i: int) -> dict:
        mem = self.members[self._find(i)]
        recs = [self.apps[m] for m in mem]
        sur = Counter(r["surname"] for r in recs).most_common(1)[0][1] / len(recs)
        ts = [r["ts"] for r in recs]
        mset = set(mem)
        kinds = Counter(k for a, b, d in self.edges if a in mset and b in mset and d["w"] >= STRONG for k in d["kinds"])
        return {"size": len(mem), "surname_share": sur, "span_days": (max(ts) - min(ts)).total_seconds() / 86400,
                "face_edges": kinds.get("face", 0), "ks_edges": kinds.get("keystroke", 0),
                "device_edges": kinds.get("device", 0), "email_edges": kinds.get("email_stem", 0),
                "members": [self.apps[m]["app_id"] for m in mem]}
