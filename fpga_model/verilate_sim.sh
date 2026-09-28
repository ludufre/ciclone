#!/usr/bin/env bash
# CICLONE M3 - Verila o wrapper sim_top (main.v REAL + memórias PSRAM/SRAM em Verilog),
# para um modelo C++ both-sides funcional (lado-MCU: SPI+memória; lado-SNES: barramento).
# Saída: build/vfpga_sim/Vsim_top__ALL.a
set -e
cd "$(dirname "$0")/.."
BASE="extern/sd2snes/verilog/sd2snes_base"
verilator --cc --build --top-module sim_top +define+MK3 \
  -Wno-fatal -Wno-lint -Wno-style -Wno-WIDTH -Wno-UNOPTFLAT -Wno-BLKANDNBLK -Wno-PINMISSING \
  -I"$BASE" -y "$BASE" -y "$BASE/ip/mk3" -y fpga_model/stubs -y fpga_model/sim \
  --Mdir build/vfpga_sim fpga_model/sim/sim_top.v
echo "OK: build/vfpga_sim/Vsim_top__ALL.a (FPGA Verilado both-sides, memória interna)"
