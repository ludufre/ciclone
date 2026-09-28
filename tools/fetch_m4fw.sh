#!/usr/bin/env bash
# Ciclone M4 - baixa o par .im3 + .elf (MESMO build, com símbolos) do host onde a firmware foi
# compilada. O lpc_emu precisa do .elf irmão do .im3 para resolver os endereços que intercepta,
# e o .elf normalmente fica só no host de build (src/obj-mk3/).
# Config (env ou .ciclone.env): SERVER (user@host), FW_SERVER_DIR (a árvore da firmware no
# host, a que tem src/obj-mk3/), OBJ (default obj-mk3). Build local: FW_OBJ_DIR=<pasta>.
set -euo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh
OBJ="${OBJ:-obj-mk3}"
mkdir -p build/m4fw
if [ -n "${FW_OBJ_DIR:-}" ]; then
  cp "$FW_OBJ_DIR/firmware.im3" "$FW_OBJ_DIR/sd2snes-intermediate.elf" build/m4fw/
  echo "OK: build/m4fw/ de $FW_OBJ_DIR"; exit 0
fi
SERVER="${SERVER:?defina SERVER=user@host e FW_SERVER_DIR (ou FW_OBJ_DIR para um build local)}"
FW_SERVER_DIR="${FW_SERVER_DIR:?defina FW_SERVER_DIR = a árvore da firmware no host de build}"
scp -q "$SERVER:$FW_SERVER_DIR/src/$OBJ/firmware.im3" "$SERVER:$FW_SERVER_DIR/src/$OBJ/sd2snes-intermediate.elf" build/m4fw/
echo "OK: build/m4fw/{firmware.im3,sd2snes-intermediate.elf} de $SERVER:$FW_SERVER_DIR/src/$OBJ"
