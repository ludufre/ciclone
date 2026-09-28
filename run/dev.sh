#!/usr/bin/env bash
# CENÁRIO: loop de dev rápido - recompila o firmware C (in-process) e REABRE a janela.
# Use depois de editar extern/sd2snes/src/*.c (não precisa do servidor de build).
set -e
cd "$(dirname "$0")/.."
echo "== recompilando o firmware (libsd2snesfw) =="
bash firmware_lib/build.sh
[ -f build/sdcard.img ] || bash tools/make_sdimg.sh
echo "== relinkando + abrindo a janela (ESC p/ sair) =="
bash host_runner/build_gui.sh
build/host_runner_gui --gui build/sdcard.img
