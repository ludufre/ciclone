#!/usr/bin/env bash
# Ciclone - the SMS core for the runner: verilates the RTL of the firmware tree when it changed
# (fpga_model/verilate_sms.sh) and prints the objects to link (stdout). Without Verilator, or
# with CICLONE_SMS=0, prints nothing: the runner links without it and an .sms boots the player
# on a silent model, as before. Log on stderr.
#   clang++ ... $(bash tools/sms_objs.sh) ...
set -e
cd "$(dirname "$0")/.."
OUT="${CICLONE_VSMS:-${CICLONE_BUILD:-build}/vsms}"
[ "${CICLONE_SMS:-1}" = "0" ] && exit 0
command -v verilator >/dev/null 2>&1 || { echo "sms: sem verilator, core SMS fora do runner" >&2; exit 0; }
bash fpga_model/verilate_sms.sh >&2
VINC="$(verilator --getenv VERILATOR_ROOT)/include"
O="$OUT/sms_model.o"
if [ ! -f "$O" ] || [ "$O" -ot "$OUT/STAMP" ] || [ "$O" -ot fpga_model/sms_model.cpp ] || [ "$O" -ot fpga_model/sms_model.h ]; then
  clang++ -std=gnu++17 -O2 -Wno-invalid-offsetof -I fpga_model -I "$OUT" -I "$VINC" -I "$VINC/vltstd" \
    -c fpga_model/sms_model.cpp -o "$O" >&2
fi
echo "$O $OUT/Vsms_core__ALL.a $OUT/libverilated.a"
