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

# the mount point comes from attach's own output (last tab field): `df | grep $DEV` can match
# /dev/disk5 against /dev/disk50s1, i.e. another mounted image, and copy the files there
ATTACH="$(hdiutil attach -nobrowse "$IMG" 2>/dev/null | tail -1)"
DEV="$(printf '%s\n' "$ATTACH" | awk '{print $1}')"
MNT="$(printf '%s\n' "$ATTACH" | awk -F'\t' '{print $NF}')"
[ -n "$DEV" ] && [ -d "$MNT" ] || { echo "mount failed"; exit 1; }
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
# per-game savestate combos and audio fixes, as a release card carries them (from the firmware tree)
for f in savestate_inputs.yml savestate_fixes.yml; do
  [ -f "$ROOT/extern/sd2snes/savestate/$f" ] && cp "$ROOT/extern/sd2snes/savestate/$f" "$MNT/sd2snes/$f"
done
printf 'CICLONE-DUMMY-FPGA-BITSTREAM' > "$MNT/sd2snes/fpga_base.bi3"
# SD_CONFIG=<arquivo>: config.yml inicial (a firmware completa as chaves que faltarem no boot)
[ -n "${SD_CONFIG:-}" ] && cp "$SD_CONFIG" "$MNT/sd2snes/config.yml"
# ResetPatch off unless the config says otherwise: with it on, the reset hook ($2A7D) times
# an H-IRQ against $4212's h-blank flag to catch a misaligned CPU/PPU clock phase and resets
# until it passes. That phase is random on a console; bsnes' timing is fixed and fails the
# check every time, so the game would reset forever.
if ! grep -qs "ResetPatch" "$MNT/sd2snes/config.yml"; then
  [ -f "$MNT/sd2snes/config.yml" ] || printf -- '---\r\n' > "$MNT/sd2snes/config.yml"
  printf 'ResetPatch: false\r\n' >> "$MNT/sd2snes/config.yml"
fi
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
# a failed detach leaves the image unflushed (empty FAT, a truncated ROM): retry, then fail
for _ in 1 2 3 4 5; do hdiutil detach "$DEV" >/dev/null 2>&1 && DEV= && break; sleep 1; done
[ -z "$DEV" ] || { echo "detach failed: $IMG"; exit 1; }

# carimbo: qual menu está nesta imagem (o tools/ensure_sd.sh recria quando ele muda)
shasum "$M3NU" "$IGM" 2>/dev/null | awk '{print $1}' > "$IMG.menu"
echo "OK: $IMG (FAT32, /sd2snes/m3nu.bin)"
ls -la "$IMG"
