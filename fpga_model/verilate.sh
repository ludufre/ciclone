#!/usr/bin/env bash
# CICLONE M3: Verila o RTL REAL do FPGA do sd2snes (sd2snes_base/main.v, Cyclone IV)
# para um modelo C++ cycle-accurate, usando os stubs comportamentais de altpll/altsyncram.
# Saída: build/vfpga/Vmain__ALL.a + Vmain.h (modelo embutível como backend B do seam #2).
set -e
cd "$(dirname "$0")/.."
BASE="extern/sd2snes/verilog/sd2snes_base"
STUBS="fpga_model/stubs"
OUT="build/vfpga"
CORE="${1:-base}"   # por ora só 'base'; outros cores (gsu/sa1/...) virão depois

verilator --cc --build --top-module main +define+MK3 \
  -Wno-fatal -Wno-lint -Wno-style -Wno-WIDTH -Wno-UNOPTFLAT -Wno-BLKANDNBLK \
  -I"$BASE" -y "$BASE" -y "$BASE/ip/mk3" -y "$STUBS" \
  --Mdir "$OUT" "$BASE/main.v"

echo "OK: modelo Verilated em $OUT (Vmain__ALL.a, Vmain.h)"
