#!/usr/bin/env bash
# CENÁRIO: roteiro de botões headless -> screenshots PNG (firmware REAL + FpgaModel).
#   bash run/keys.sh "<keys>" "<shots>" [frames] [sdimg]
#   keys : "F:BTN[+BTN][:HOLD],..."  (BTN = B Y SEL START UP DOWN LEFT RIGHT A X L R;
#          HOLD em quadros, default 4)
#   shots: "F:nome,..."               grava build/shots/<nome>.png depois do quadro F
# Ex. (Y numa pasta MSU-1):
#   bash run/keys.sh "120:DOWN,160:Y" "150:antes,260:depois"
# O log da firmware vai para build/shots/run.log.
set -e
cd "$(dirname "$0")/.."
KEYS="${1:?keys}"; SHOTS="${2:?shots}"; FRAMES="${3:-}"; IMG="${4:-build/sdcard.img}"
if [ "$IMG" = build/sdcard.img ]; then bash tools/ensure_sd.sh >/dev/null; else [ -f "$IMG" ] || bash tools/make_sdimg.sh "$IMG" >/dev/null; fi
[ -x build/host_runner_fw ] || bash tools/build_all.sh
mkdir -p build/shots
PPMS=""; LAST=0
IFS=',' read -ra EV <<< "$SHOTS"
for e in "${EV[@]}"; do
  f="${e%%:*}"; n="${e#*:}"
  PPMS="$PPMS,$f:build/shots/$n.ppm"; [ "$f" -gt "$LAST" ] && LAST="$f"
done
[ -n "$FRAMES" ] || FRAMES=$((LAST + 1))
build/host_runner_fw --fw --keys "$KEYS" --shots "${PPMS#,}" "$IMG" build/shots/last.ppm "$FRAMES" > build/shots/run.log 2>&1
for e in "${EV[@]}"; do
  n="${e#*:}"
  python3 tools/ppm2png.py "build/shots/$n.ppm" "build/shots/$n.png" >/dev/null && rm -f "build/shots/$n.ppm"
  echo "build/shots/$n.png"
done
