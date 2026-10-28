#!/usr/bin/env bash
# Full offline build: population -> features -> model/metrics -> attack lab -> SQLite.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
N=${N:-1400}
WORKERS=${WORKERS:-4}
$PY backend/app/modules/document/checksums.py
$PY -c "import sys; sys.path.insert(0,'backend'); from app.modules.document import dates; dates.test(); from app.modules.correlation import fuzzy; fuzzy.test(); print('self-checks ok')"
$PY data/gen_population.py --n "$N"
$PY eval/build_dataset.py "$WORKERS"
$PY eval/train.py
$PY eval/adaptive_attacker.py
$PY eval/run_attacks.py "$WORKERS"
$PY eval/seed_db.py
echo "build complete"
