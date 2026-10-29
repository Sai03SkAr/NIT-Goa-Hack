#!/usr/bin/env bash
# Full offline build: population -> features -> model/metrics -> attack lab -> SQLite.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x .venv/Scripts/python.exe ] && PY=.venv/Scripts/python.exe  # Windows (Git Bash)
N=${N:-1400}
WORKERS=${WORKERS:-4}
$PY backend/app/modules/document/checksums.py
$PY -c "import sys; sys.path.insert(0,'backend'); from app.modules.document import dates; dates.test(); from app.modules.correlation import fuzzy; fuzzy.test(); print('self-checks ok')"
LFW=data/lfw/lfw_home/lfw-funneled.tgz
if [ ! -f "$LFW" ]; then  # ~243 MB; parallel ranges because some networks throttle single connections
  mkdir -p data/lfw/lfw_home/parts
  URL=https://ndownloader.figshare.com/files/5976015 TOTAL=243346528 PARTS=12
  CH=$(( (TOTAL + PARTS - 1) / PARTS ))
  for i in $(seq 0 $((PARTS-1))); do
    S=$((i*CH)); E=$((S+CH-1)); [ $E -ge $TOTAL ] && E=$((TOTAL-1))
    curl -sfL -r $S-$E -o data/lfw/lfw_home/parts/p$(printf %02d $i) "$URL" &
  done
  wait
  cat data/lfw/lfw_home/parts/p* > "$LFW" && rm -rf data/lfw/lfw_home/parts
  tar -tzf "$LFW" > /dev/null  # fail fast on a corrupt archive
fi
$PY data/gen_population.py --n "$N"
rm -rf precomputed/extract  # cached extractions belong to the previous population and code
$PY eval/build_dataset.py "$WORKERS"
$PY data/gen_footprint.py  # needs the face embeddings build_dataset computed
$PY eval/augment.py
$PY eval/train.py
$PY eval/adaptive_attacker.py
$PY eval/vae_attacker.py
$PY eval/federated_profile.py
$PY eval/footprint_eval.py
$PY eval/run_attacks.py "$WORKERS"
$PY eval/seed_db.py
echo "build complete"
