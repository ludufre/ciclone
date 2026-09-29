#!/usr/bin/env bash
# Ciclone - build a FAT32 SD image (build/sdcard.img) holding /sd2snes/m3nu.bin,
# the file the firmware mounts and boots. macOS-native (hdiutil + newfs_msdos);
# no mtools needed. Re-run to regenerate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${1:-$ROOT/build/sdcard.img}"
# menu: $M3NU, senão o MAIS RECENTE entre o bin/ do seu build da firmware e o pacote do
# tools/build_menu.sh (build/menu/). O igmenu.bin vem da mesma pasta, para o par não se misturar.
MENU_DIR="$(bash "$ROOT/tools/menu_dir.sh")"
M3NU="${M3NU:-$MENU_DIR/m3nu.bin}"
SIZE_MB="${SIZE_MB:-48}"   # >= ~32 MB so newfs_msdos picks FAT32

[ -f "$M3NU" ] || { echo "sem m3nu.bin ($M3NU): builde a firmware ou rode tools/build_menu.sh"; exit 1; }
echo "menu: $M3NU"
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
# first-boot tour ROM, from the same folder as the menu (SD_NO_ONBOARDING=1 leaves it out)
ONB="${ONBOARDING:-$(dirname "$M3NU")/onboarding.bin}"
[ -f "$ONB" ] && [ "${SD_NO_ONBOARDING:-0}" != "1" ] && cp "$ONB" "$MNT/sd2snes/onboarding.bin"
# the release's sound files and the tour's welcome clip (misc/ of the sd2snes tree);
# SD_MISC=0 leaves them out (the test harness does, unless a test asks)
if [ "${SD_MISC:-1}" = "1" ]; then
  for f in menu.spc sfx_cursor.pcm sfx_confirm.pcm sfx_back.pcm sfx_error.pcm welcome.fmv welcome.pcm; do
    [ -f "$ROOT/extern/sd2snes/misc/$f" ] && cp "$ROOT/extern/sd2snes/misc/$f" "$MNT/sd2snes/$f"
  done
fi
IGM="${IGMENU:-$(dirname "$M3NU")/igmenu.bin}"
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

# carimbo: qual menu está nesta imagem (o tools/ensure_sd.sh recria quando ele muda)
shasum "$M3NU" "$IGM" 2>/dev/null | awk '{print $1}' > "$IMG.menu"
echo "OK: $IMG (FAT32, /sd2snes/m3nu.bin)"
ls -la "$IMG"
