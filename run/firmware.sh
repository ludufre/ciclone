#!/usr/bin/env bash
# CENÁRIO: bootar o .im3 REAL no emulador LPC1756 (Unicorn) e ver o log do firmware.
# Opcional: passe um caminho de .im3 (default = build/m4fw/firmware.im3, baixado do servidor
# de build por tools/fetch_m4fw.sh junto com o .elf irmão).
set -e
cd "$(dirname "$0")/.."
[ -f build/sdcard.img ] || bash tools/make_sdimg.sh
bash m4_unicorn/build.sh
[ -n "${1:-}" ] || [ -f build/m4fw/sd2snes-intermediate.elf ] || bash tools/fetch_m4fw.sh
IM3="${1:-build/m4fw/firmware.im3}"
echo "== rodando $IM3 (log limpo) =="
build/lpc_emu "$IM3" 2>&1 | grep -vE "CIC toggle|syscon|i=[0-9]+ val="
