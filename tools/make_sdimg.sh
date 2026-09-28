#!/usr/bin/env bash
# Ciclone - build a FAT32 SD image (build/sdcard.img) holding /sd2snes/m3nu.bin,
# the file the firmware mounts and boots. macOS-native (hdiutil + newfs_msdos);
# no mtools needed. Re-run to regenerate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${1:-$ROOT/build/sdcard.img}"
# menu: $M3NU, senão o bin/ do seu build da firmware, senão o pacote do tools/build_menu.sh
pick() { for f in "$@"; do [ -f "$f" ] && { echo "$f"; return; }; done; echo "$1"; }
M3NU="${M3NU:-$(pick "$ROOT/extern/sd2snes/bin/m3nu.bin" "$ROOT/build/menu/m3nu.bin")}"
SIZE_MB="${SIZE_MB:-48}"   # >= ~32 MB so newfs_msdos picks FAT32

[ -f "$M3NU" ] || { echo "sem m3nu.bin ($M3NU): builde a firmware ou rode tools/build_menu.sh"; exit 1; }
mkdir -p "$(dirname "$IMG")"
rm -f "$IMG"
dd if=/dev/zero of="$IMG" bs=1m count="$SIZE_MB" 2>/dev/null

DEV="$(hdiutil attach -nomount "$IMG" 2>/dev/null | head -1 | awk '{print $1}')"
newfs_msdos -F 32 -v SD2SNES "$DEV" >/dev/null 2>&1
hdiutil detach "$DEV" >/dev/null 2>&1

DEV="$(hdiutil attach -nobrowse "$IMG" 2>/dev/null | head -1 | awk '{print $1}')"
MNT="$(df 2>/dev/null | grep "$DEV" | awk '{print $NF}' | head -1)"
[ -n "$MNT" ] || { echo "mount failed"; exit 1; }
mkdir -p "$MNT/sd2snes"
cp "$M3NU" "$MNT/sd2snes/m3nu.bin"
ONB="$ROOT/extern/sd2snes/bin/onboarding.bin"
[ -f "$ONB" ] && cp "$ONB" "$MNT/sd2snes/onboarding.bin"   # onboarding tour ROM
IGM="${IGMENU:-$(pick "$ROOT/extern/sd2snes/bin/igmenu.bin" "$ROOT/build/menu/igmenu.bin")}"
[ -f "$IGM" ] && cp "$IGM" "$MNT/sd2snes/igmenu.bin"          # in-game menu shell (bank $C8)
printf 'CICLONE-DUMMY-FPGA-BITSTREAM' > "$MNT/sd2snes/fpga_base.bi3"
# SD_CONFIG=<arquivo>: config.yml inicial (a firmware completa as chaves que faltarem no boot)
[ -n "${SD_CONFIG:-}" ] && cp "$SD_CONFIG" "$MNT/sd2snes/config.yml"
# arvore de teste (ROM solta, pasta MSU-1, pasta com 2 ROMs, pasta vazia); SD_FIXTURES=0 desliga.
# COPYFILE_DISABLE + -X: sem os ._* (AppleDouble) do macOS, que o FAT listaria como lixo.
if [ "${SD_FIXTURES:-1}" = "1" ]; then
  python3 "$ROOT/tools/sd_fixtures.py" "$ROOT/build/sd_fixtures" >/dev/null
  COPYFILE_DISABLE=1 cp -RX "$ROOT/build/sd_fixtures/" "$MNT/"
fi
# SD_EXTRA=<dir>: árvore copiada por cima (arquivos específicos de um teste)
[ -n "${SD_EXTRA:-}" ] && COPYFILE_DISABLE=1 cp -RX "$SD_EXTRA/" "$MNT/"
# o kernel do macOS grava ._* (xattrs como com.apple.provenance) em FAT mesmo com cp -X;
# apagar o ._ apaga o xattr. Os metadados de volume do macOS também saem (o browser do
# menu listaria .fseventsd como pasta).
rm -rf "$MNT/.fseventsd" "$MNT/.Spotlight-V100" "$MNT/.Trashes" 2>/dev/null || true
find "$MNT" -name '._*' -delete 2>/dev/null || true
sync
hdiutil detach "$DEV" >/dev/null 2>&1

echo "OK: $IMG (FAT32, /sd2snes/m3nu.bin)"
ls -la "$IMG"
