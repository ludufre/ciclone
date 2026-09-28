#!/usr/bin/env bash
# CENÁRIO: abrir o menu do sd2snes numa JANELA interativa (firmware real + FpgaModel).
# Controles: Setas=D-pad  Z=B X=A A=Y S=X  Enter=Start Shift=Select  Q=L W=R  ESC=sair
set -e
cd "$(dirname "$0")/.."
bash tools/ensure_sd.sh
bash host_runner/build_gui.sh
echo "== abrindo a janela (ESC p/ sair) =="
build/host_runner_gui --gui build/sdcard.img
