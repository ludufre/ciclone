#!/usr/bin/env bash
# CICLONE M4 - emulador LPC1756 (Cortex-M3) via Unicorn, rodando o .im3 REAL,
# com o SSP do firmware ligado ao FpgaModel comportamental (o MESMO do M2/M3) pelo seam SPI.
# Requer: brew install unicorn.
set -e
cd "$(dirname "$0")/.."
mkdir -p build
clang   -O2 -I /opt/homebrew/include            -c m4_unicorn/lpc_emu.c   -o build/lpc_emu.o
clang++ -std=gnu++17 -O2 -I include -I fpga_model -c fpga_model/behavioral.cpp -o build/behavioral_m4.o
clang++ -std=gnu++17 -O2 -I include -I fpga_model -c m4_unicorn/m4_glue.cpp    -o build/m4_glue.o
clang++ -O2 build/lpc_emu.o build/behavioral_m4.o build/m4_glue.o -L /opt/homebrew/lib -lunicorn -o build/lpc_emu
echo "OK: build/lpc_emu"
echo "Rode: bash tools/fetch_m4fw.sh && build/lpc_emu build/m4fw/firmware.im3"
