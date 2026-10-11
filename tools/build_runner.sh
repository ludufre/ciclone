#!/usr/bin/env bash
# Ciclone - the headless runner (build/host_runner_fw): the firmware C of the tree + bsnes +
# the FPGA model, with the SMS core as RTL when Verilator is there (tools/sms_objs.sh).
# The same link run/test_menu.sh does; for scripts that need the runner and nothing else
# (tools/sms_run.py). CICLONE_BUILD=<dir>: everything in that dir instead of build/ (one per
# firmware tree, so runs against two trees do not rebuild each other's runner).
set -e
cd "$(dirname "$0")/.."
B="${CICLONE_BUILD:-build}"
mkdir -p "$B"
BSNES=extern/bsnes-plus/bsnes
[ -f "$BSNES/out/libsnes.a" ] || ( cd "$BSNES" && make platform=osx profile=compatibility library >/dev/null )
bash firmware_lib/build.sh >/dev/null
SMS_OBJS="$(bash tools/sms_objs.sh)"
clang++ -std=gnu++17 -O2 -I include -I fpga_model -I "$BSNES/snes/libsnes" \
  host_runner/runner.cpp fpga_model/behavioral.cpp "$B/libsd2snesfw.a" "$BSNES/out/libsnes.a" \
  $SMS_OBJS -o "$B/host_runner_fw" -lpthread
echo "OK: $B/host_runner_fw${SMS_OBJS:+ (core SMS: $(cat "${CICLONE_VSMS:-$B/vsms}/SRC"))}"
