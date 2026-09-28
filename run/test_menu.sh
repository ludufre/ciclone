#!/usr/bin/env bash
# CENÁRIO: suíte automatizada do MENU (firmware real + menu real, sem hardware).
#   bash run/test_menu.sh                 # builda o menu do working tree no servidor e roda tudo
#   bash run/test_menu.sh -k msu -v       # args vão para tests/menu/run.py
#   NO_BUILD=1 bash run/test_menu.sh      # reusa build/menu (sem ir ao servidor)
#   REF=HEAD bash run/test_menu.sh        # testa o MENU de um commit (a firmware C segue a do working tree)
set -e
cd "$(dirname "$0")/.."
[ -f extern/bsnes-plus/bsnes/out/libsnes.a ] || bash tools/build_all.sh
# a firmware C do working tree, sempre (~5 s): a suíte roda o MCU real linkado no runner, e sem
# isto uma mudança em src/*.c seria testada contra o runner da build anterior
bash firmware_lib/build.sh >/dev/null
BSNES=extern/bsnes-plus/bsnes
clang++ -std=gnu++17 -O2 -I include -I fpga_model -I "$BSNES/snes/libsnes" \
  host_runner/runner.cpp fpga_model/behavioral.cpp build/libsd2snesfw.a "$BSNES/out/libsnes.a" \
  -o build/host_runner_fw -lpthread
if [ -z "${NO_BUILD:-}" ]; then
  if [ -n "${REF:-}" ]; then
    DEST="build/menu-$(echo "$REF" | tr '/' '_')"
    SERVER_DIR=ciclone-menu-ref bash tools/build_menu.sh "$DEST"
    export CICLONE_MENU="$PWD/$DEST"
  else
    bash tools/build_menu.sh
  fi
fi
python3 tests/menu/run.py "$@"
