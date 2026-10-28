#!/usr/bin/env bash
# Fetch TruFor (CVPR 2023, grip-unina) inference code + trained weights into models/trufor/.
# Not committed to this repo: TruFor's license is research / non-commercial. ~261 MB download.
set -euo pipefail
cd "$(dirname "$0")/.."
DST=models/trufor
RAW=https://raw.githubusercontent.com/grip-unina/TruFor/main/test_docker/src
mkdir -p $DST/src/models/cmx/{decoders,encoders,utils}

for f in config.py data_core.py trufor.yaml trufor_test.py models/__init__.py models/DnCNN.py \
         models/cmx/__init__.py models/cmx/builder_np_conf.py models/cmx/layer_utils.py models/cmx/net_utils.py \
         models/cmx/decoders/MLPDecoder.py models/cmx/encoders/dual_segformer.py \
         models/cmx/utils/__init__.py models/cmx/utils/init_func.py; do
  curl -sfL "$RAW/$f" -o "$DST/src/$f"
done
touch $DST/src/models/cmx/decoders/__init__.py $DST/src/models/cmx/encoders/__init__.py

ZIP=$DST/TruFor_weights.zip
if [ ! -f $DST/weights/trufor.pth.tar ]; then
  URL=https://www.grip.unina.it/download/prog/TruFor/TruFor_weights.zip TOTAL=260878690 PARTS=12
  CH=$(( (TOTAL + PARTS - 1) / PARTS )); mkdir -p $DST/parts
  for i in $(seq 0 $((PARTS-1))); do
    S=$((i*CH)); E=$((S+CH-1)); [ $E -ge $TOTAL ] && E=$((TOTAL-1))
    curl -sfL --retry 5 -r $S-$E -o $DST/parts/p$(printf %02d $i) "$URL" &
  done
  wait
  cat $DST/parts/p* > $ZIP && rm -rf $DST/parts
  [ "$(md5 -q $ZIP 2>/dev/null || md5sum $ZIP | cut -d' ' -f1)" = "7bee48f3476c75616c3c5721ab256ff8" ] || { echo "MD5 mismatch"; exit 1; }
  unzip -q -o $ZIP -d $DST && rm $ZIP
fi
VIRTUAL_ENV=.venv uv pip install -q yacs timm
ls -la $DST/weights
echo "TruFor ready"
