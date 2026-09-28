#!/usr/bin/env bash
# Ciclone - host_runner com JANELA interativa (SDL): mesmo core libsnes + chip sd2snes +
# firmware REAL + FpgaModel do --fw, mas com tela e teclado. Requer: brew install sdl2.
set -e
cd "$(dirname "$0")/.."
BSNES="extern/bsnes-plus/bsnes"
mkdir -p build
[ -f build/libsd2snesfw.a ] || bash firmware_lib/build.sh
[ -f "$BSNES/out/libsnes.a" ] || ( cd "$BSNES" && make platform=osx profile=compatibility library )
clang++ -std=gnu++17 -O2 -DCICLONE_SDL $(sdl2-config --cflags) \
  -I include -I fpga_model -I "$BSNES/snes/libsnes" \
  host_runner/runner.cpp fpga_model/behavioral.cpp \
  build/libsd2snesfw.a "$BSNES/out/libsnes.a" $(sdl2-config --libs) -lpthread \
  -o build/host_runner_gui
echo "OK: build/host_runner_gui"
echo "Rode: build/host_runner_gui --gui build/sdcard.img"
