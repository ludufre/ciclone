#!/usr/bin/env bash
# Ciclone - the SMS player (snes/sms/sms_snes.asm, the SNES side of the SMS core) of the
# firmware tree, assembled to build/sms/sms_snes.bin. The player and the core ship as a pair,
# so a test of the core uses the player of the SAME tree.
#   bash tools/build_sms_player.sh            (tree: CICLONE_TREE, else extern/sd2snes; out:
#                                              $CICLONE_BUILD/sms/, default build/sms/)
# Assembler: asar (Asar 1.x, the SNES one -- not the Electron archiver of the same name):
# ASAR=<path> (env or .ciclone.env), else `asar` on the PATH when it is the right one, else
# the build host (SERVER, where prepare.sh installs it), else the tree's misc/sms_snes.bin
# when it is at least as new as the .asm. CICLONE_SMS_PLAYER=<file> skips all that.
set -euo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh
TREE="${CICLONE_TREE:-extern/sd2snes}"
SRC="$TREE/snes/sms/sms_snes.asm"
OUT="${CICLONE_BUILD:-build}/sms/sms_snes.bin"
mkdir -p "$(dirname "$OUT")"
if [ -n "${CICLONE_SMS_PLAYER:-}" ]; then cp "$CICLONE_SMS_PLAYER" "$OUT"; echo "OK: $OUT <- $CICLONE_SMS_PLAYER"; exit 0; fi
[ -f "$SRC" ] || { echo "sem $SRC"; exit 1; }
SUM="$( (echo "$(cd "$(dirname "$SRC")" && pwd)"; cat "$SRC") | shasum | cut -c1-16)"
[ -f "$OUT" ] && [ "$(cat "$OUT.stamp" 2>/dev/null)" = "$SUM" ] && { echo "OK: $OUT em dia"; exit 0; }
is_asar() { "$1" --version 2>/dev/null | grep -q '^Asar '; }
A="${ASAR:-}"
[ -n "$A" ] || { command -v asar >/dev/null 2>&1 && is_asar asar && A=asar; } || true
rm -f "$OUT"
if [ -n "$A" ]; then
  ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
  ( cd "$(dirname "$SRC")" && "$A" sms_snes.asm "$ABS" ) >/dev/null
elif [ -n "${SERVER:-}" ]; then
  D="${SMS_SERVER_DIR:-ciclone-sms-player}"
  ssh "$SERVER" "mkdir -p $D" && scp -q "$SRC" "$SERVER:$D/sms_snes.asm"
  ssh "$SERVER" "cd $D && asar sms_snes.asm sms_snes.bin >/dev/null" && scp -q "$SERVER:$D/sms_snes.bin" "$OUT"
elif [ -f "$TREE/misc/sms_snes.bin" ] && [ ! "$TREE/misc/sms_snes.bin" -ot "$SRC" ]; then
  cp "$TREE/misc/sms_snes.bin" "$OUT"
fi
[ -s "$OUT" ] || { echo "sms_snes.bin: sem asar (ASAR=...), sem SERVER e sem misc/sms_snes.bin em dia"; exit 1; }
echo "$SUM" > "$OUT.stamp"
echo "OK: $OUT <- $SRC"
