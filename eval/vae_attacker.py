"""Generative adversarial attacker (after IDRBT's chaotic VAE adversarial ML, Reddy, Vivek, Pranay, Ravi, arXiv 2302.12959).

A variational autoencoder learns what GENUINE applicants' controllable signals look like (typing, timing, velocity,
device and graph links). For every fraud the system caught, the attacker swaps in 64 decoded samples, drawn either with
Gaussian latent noise or with the logistic-map chaos IDRBT uses to explore the latent space, and wins if any sample is
approved. Unlike the greedy attacker, every sample is a realistic, internally consistent genuine profile.

Compared on: the live system (model + evidence policy), and a behaviour-and-graph-only detector (what a system that
only watches sessions would be). Output: an entry in precomputed/attacks.json (Attack Lab) and precomputed/vae_attack.json."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.isotonic import IsotonicRegression
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import train as T  # noqa: E402
from adaptive_attacker import controllable  # noqa: E402
from app.config import BANDS, PRE  # noqa: E402
from app.fusion.model import decide  # noqa: E402

Z, SAMPLES = 8, 64


class VAE(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, 2 * Z))
        self.dec = nn.Sequential(nn.Linear(Z, 64), nn.ReLU(), nn.Linear(64, d))

    def forward(self, x):
        m, lv = self.enc(x).chunk(2, -1)
        return self.dec(m + torch.randn_like(m) * (0.5 * lv).exp()), m, lv


def logistic_map(n, x0=0.37, r=3.99):
    """Chaotic sequence in (0, 1); mapped to roughly [-3, 3] per latent dimension."""
    out, x = np.empty(n * Z), x0
    for i in range(n * Z):
        x = r * x * (1 - x)
        out[i] = x
    return torch.tensor((out.reshape(n, Z) - 0.5) * 6, dtype=torch.float32)


def main():
    torch.manual_seed(0)
    df, feats = T.load()
    tr, ca, te = T.split(df)
    cols = [c for c in df.columns if c.split("_")[0] in ("doc", "bio", "beh", "reg", "cor", "ev", "meta")]
    ctrl = controllable(cols)
    G = tr[tr.label == 0][ctrl].astype(float)
    Gf = G.fillna(G.median().fillna(0))
    mu, sd = Gf.mean(), Gf.std().replace(0, 1).fillna(1)
    X = torch.tensor(((Gf - mu) / sd).values, dtype=torch.float32)
    vae = VAE(X.shape[1])
    opt = torch.optim.Adam(vae.parameters(), 1e-3)
    for _ in range(400):
        r, m, lv = vae(X)
        loss = ((r - X) ** 2).sum(1).mean() + (-0.5 * (1 + lv - m ** 2 - lv.exp()).sum(1)).mean()
        opt.zero_grad(); loss.backward(); opt.step()

    def samples(chaotic):
        with torch.no_grad():
            lat = logistic_map(SAMPLES) if chaotic else torch.randn(SAMPLES, Z)
            S = vae.dec(lat).numpy() * sd.values + mu.values
        return np.clip(np.nan_to_num(S), Gf.min().values, Gf.max().values)  # stay inside what genuine people show

    # a session-only detector for contrast: behaviour + graph features only
    bcols = [c for c in feats if c.startswith(("beh_", "cor_"))]
    bm = T.fit(tr, bcols)
    biso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(T.proba(bm, ca, bcols), ca.label.values)

    fraud = te[te.label == 1]
    base = {r.app_id: {c: (np.nan if pd.isna(getattr(r, c)) else getattr(r, c)) for c in cols} for r in fraud.itertuples()}
    live_caught = [a for a, f in base.items() if decide(f)["band"] != "APPROVE"]
    beh_prob = lambda f: float(biso.predict(T.proba(bm, pd.DataFrame([f])[bcols], bcols))[0])
    beh_caught = [a for a, f in base.items() if beh_prob(f) >= BANDS["approve_below"]]

    rows, result = [], {}
    for name, chaotic in (("Gaussian VAE", False), ("Chaotic VAE (logistic map)", True)):
        S = samples(chaotic)
        live_ev = sum(any(decide({**base[a], **dict(zip(ctrl, s))})["band"] == "APPROVE" for s in S) for a in live_caught)
        beh_ev = sum(any(beh_prob({**base[a], **dict(zip(ctrl, s))}) < BANDS["approve_below"] for s in S) for a in beh_caught)
        result[name] = {"live_evaded": live_ev, "live_caught": len(live_caught), "beh_evaded": beh_ev, "beh_caught": len(beh_caught)}
        rows += [{"detector": f"{name}: frauds turned into an approval, full system", "value": f"{live_ev} of {len(live_caught)}"},
                 {"detector": f"{name}: frauds slipping past a behaviour-only detector", "value": f"{beh_ev} of {len(beh_caught)}"}]
        print(name, result[name])
    entry = {"id": "vae", "kind": "single", "name": "Generative attacker (chaotic VAE)",
             "target": "Behaviour, graph", "n": len(live_caught),
             "defense": "Realistic genuine-looking sessions can't fix evidence the attacker can't fake (documents, face, registry)",
             "source": "after IDRBT, Reddy, Vivek, Pranay, Ravi, arXiv 2302.12959", "rows": rows,
             "controllable_features": len(ctrl), "samples_per_case": SAMPLES}
    (PRE / "vae_attack.json").write_text(json.dumps({"entry": entry, "result": result}, indent=1))
    att = PRE / "attacks.json"
    if att.exists():  # add/replace in place so the Attack Lab shows it without re-running every sweep
        a = json.loads(att.read_text())
        a["attacks"] = [x for x in a["attacks"] if x.get("id") != "vae"] + [entry]
        att.write_text(json.dumps(a, indent=1, default=float))
    print("wrote vae_attack.json")


if __name__ == "__main__":
    main()
