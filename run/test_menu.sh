#!/usr/bin/env bash
# CENÁRIO: suíte automatizada do MENU (firmware real + menu real, sem hardware).
#   bash run/test_menu.sh                 # builda o menu do working tree no servidor e roda tudo
#   bash run/test_menu.sh -k msu -v       # args vão para tests/menu/run.py
#   NO_BUILD=1 bash run/test_menu.sh      # reusa build/menu (sem ir ao servidor)
#   REF=HEAD bash run/test_menu.sh        # testa o MENU de um commit (a firmware C segue a do working tree)
#   COVERAGE=1 bash run/test_menu.sh      # + cobertura de linhas da firmware C (build/coverage/report.txt)
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
if [ -z "${COVERAGE:-}" ]; then
  python3 tests/menu/run.py "$@"
  exit
fi
# COVERAGE=1: the same suite on a runner whose firmware is instrumented (clang source-based
# coverage), linked apart as host_runner_fw_cov so the normal runner never writes profiles.
# The library is rebuilt plain right after: run/menu.sh and keys.sh link against it.
COV=build/coverage
rm -rf "$COV" && mkdir -p "$COV"
CC="clang -fprofile-instr-generate -fcoverage-mapping" bash firmware_lib/build.sh >/dev/null
clang -c host_runner/cov_exit.c -o "$COV/cov_exit.o"
clang++ -std=gnu++17 -O2 -fprofile-instr-generate -D_exit=cov_exit -I include -I fpga_model \
  -I "$BSNES/snes/libsnes" host_runner/runner.cpp fpga_model/behavioral.cpp build/libsd2snesfw.a \
  "$BSNES/out/libsnes.a" "$COV/cov_exit.o" -o build/host_runner_fw_cov -lpthread
bash firmware_lib/build.sh >/dev/null
set +e
LLVM_PROFILE_FILE="$PWD/$COV/%p.profraw" CICLONE_RUNNER="$PWD/build/host_runner_fw_cov" \
  python3 tests/menu/run.py "$@"
rc=$?
set -e
xcrun llvm-profdata merge -o "$COV/all.profdata" "$COV"/*.profraw
xcrun llvm-cov report build/host_runner_fw_cov -instr-profile="$COV/all.profdata" 2>/dev/null \
  | grep 'fw_src/' | awk '{f=$1; sub(".*/", "", f); L+=$8; M+=$9;
      printf "%-18s %6d linhas  %7s\n", f, $8, $10}
      END {printf "%-18s %6d linhas  %6.2f%%\n", "FIRMWARE", L, 100 * (L - M) / L}' \
  | tee "$COV/report.txt"
echo "(por função: xcrun llvm-cov report build/host_runner_fw_cov -instr-profile=$COV/all.profdata -show-functions build/fw_src/<arquivo>.c)"
exit $rc
