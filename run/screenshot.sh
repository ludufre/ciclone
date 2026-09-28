#!/usr/bin/env bash
# CENÁRIO: gerar um screenshot do menu (headless, sem janela) e abrir. Bom p/ scripts/CI.
# Opcional: passe o nº de frames a rodar antes da captura (default 180).
set -e
cd "$(dirname "$0")/.."
BSNES="extern/bsnes-plus/bsnes"
[ -f build/sdcard.img ] || bash tools/make_sdimg.sh
[ -f build/libsd2snesfw.a ] || bash firmware_lib/build.sh
[ -f "$BSNES/out/libsnes.a" ] || ( cd "$BSNES" && make platform=osx profile=compatibility library )
clang++ -std=gnu++17 -O2 -I include -I fpga_model -I "$BSNES/snes/libsnes" \
  host_runner/runner.cpp fpga_model/behavioral.cpp \
  build/libsd2snesfw.a "$BSNES/out/libsnes.a" -o build/host_runner_fw -lpthread
build/host_runner_fw --fw build/sdcard.img build/frame_fw.ppm "${1:-180}"
python3 tools/ppm2png.py build/frame_fw.ppm build/frame_fw.png
echo "OK: build/frame_fw.png"
open build/frame_fw.png 2>/dev/null || true
