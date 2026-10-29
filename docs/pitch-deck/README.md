# Pitch deck (7 slides)

The source of the PS3 pitch deck, built with Claude Design's Slides type. Each slide is one `slides/<id>.html` file, and `deck.json` gives the order, sections and fonts (Bricolage Grotesque and Geist).

| # | Slide | What it says |
|---|---|---|
| 1 | `cover` | TrueID Shield: *Trust no single check.* |
| 2 | `problem` | The PS3 problem: a synthetic identity passes every check on its own. It is real + invented, cheap to make and built to scale |
| 3 | `hierarchy` | Hierarchy chart: the problem → three ways through (forged identity, faked presence, fraud at scale) → our answer to each |
| 4 | `pipeline` | End-to-end pipeline: capture → seven checks in parallel → fuse → evidence-policy decision → explain and learn |
| 5 | `innovation` | What's new, with **fair social scoring** highlighted (1.4% vs 20.3% of genuine people flagged) |
| 6 | `proof` | Measured: 100% recall, ROC-AUC 0.998, 95% reject precision, 0/85 for an adaptive attacker; signed QR vs pixel forensics |
| 7 | `close` | Built for banks: partner API, regulation, honest limits |

The live deck (present, comment, export to PDF or PowerPoint) is the owner's Claude artifact. It is private until shared from its Share menu. To rebuild it elsewhere, create a deck from Claude's Slides type and publish these files under `project/` (`project/deck.json`, `project/slides/*.html`).
