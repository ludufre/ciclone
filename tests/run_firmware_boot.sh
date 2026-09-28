#!/usr/bin/env bash
# Ciclone - build everything and run the firmware boot smoke test end to end:
#   1. (re)build libsd2snesfw.a            (firmware_lib/build.sh)
#   2. (re)build the FAT32 SD image         (tools/make_sdimg.sh) if missing
#   3. compile + link the test with behavioral.cpp
#   4. run it (firmware boots against the FpgaModel; trace + milestones printed)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
IMG="$BUILD/sdcard.img"
CXX="${CXX:-clang++}"

bash "$ROOT/firmware_lib/build.sh"
[ -f "$IMG" ] || bash "$ROOT/tools/make_sdimg.sh" "$IMG"

echo "== compiling test_firmware_boot =="
$CXX -std=gnu++17 -O1 -g -I "$ROOT/include" -I "$ROOT/fpga_model" \
  "$ROOT/tests/test_firmware_boot.cpp" "$ROOT/fpga_model/behavioral.cpp" \
  "$BUILD/libsd2snesfw.a" -o "$BUILD/test_firmware_boot"

echo "== running (watchdog ${WATCHDOG_MS:-8000} ms) =="
"$BUILD/test_firmware_boot" "$IMG" "${WATCHDOG_MS:-8000}"
