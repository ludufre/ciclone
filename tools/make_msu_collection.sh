#!/usr/bin/env bash
# Ciclone - a card holding a big folder of REAL MSU-1 games, for the listing-cost test
# (tests/menu/test_msu_folder_scan.py, CICLONE_MSU_COLLECTION). Game folders never go into the
# repo: pass your own, each one holding a ROM, its .msu and its .pcm tracks. They are copied in
# turn, with a counter on the folder name, until COUNT folders exist under /MSU Collection.
#
#   bash tools/make_msu_collection.sh OUT.img GAME_DIR...      (COUNT=300 by default)
#
# FAT32 with 32 KB clusters (a real card's geometry); the image is sparse but the copied data is
# real, so it takes about COUNT x the average game size of disk.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$1"; shift
COUNT="${COUNT:-300}"
[ $# -gt 0 ] || { echo "usage: $0 OUT.img GAME_DIR..."; exit 1; }

total=0
for g in "$@"; do total=$((total + $(du -sk "$g" | cut -f1))); done
need_mb=$(( total / 1024 * COUNT / $# + 4096 ))
echo "$# source games, $COUNT folders, ~$((need_mb / 1024)) GB"

cfg="$(mktemp)"
printf -- '---\r\nOnboardingVersion: 255\r\nBootIntro: false\r\n' > "$cfg"
SIZE_MB="$need_mb" SD_CLUSTER=64 SD_MISC=0 SD_CONFIG="$cfg" \
  M3NU="${M3NU:-$ROOT/build/menu/m3nu.bin}" IGMENU="${IGMENU:-$ROOT/build/menu/igmenu.bin}" \
  bash "$ROOT/tools/make_sdimg.sh" "$OUT" >/dev/null
rm -f "$cfg"

ATTACH="$(hdiutil attach -nobrowse "$OUT" 2>/dev/null | tail -1)"
DEV="$(printf '%s\n' "$ATTACH" | awk '{print $1}')"
MNT="$(printf '%s\n' "$ATTACH" | awk -F'\t' '{print $NF}')"
[ -n "$DEV" ] && [ -d "$MNT" ] || { echo "mount failed"; exit 1; }
mkdir -p "$MNT/MSU Collection"
games=("$@")
for ((i = 0; i < COUNT; i++)); do
  g="${games[$((i % ${#games[@]}))]}"
  dst="$MNT/MSU Collection/$(basename "$g") $(printf '%03d' $((i + 1)))"
  COPYFILE_DISABLE=1 cp -RX "$g" "$dst"
  [ $(((i + 1) % 25)) -eq 0 ] && echo "  $((i + 1))/$COUNT"
done
find "$MNT" -name '._*' -delete 2>/dev/null || true
rm -rf "$MNT/.fseventsd" "$MNT/.Spotlight-V100" "$MNT/.Trashes" 2>/dev/null || true
du -sh "$MNT/MSU Collection"
find "$MNT/MSU Collection" -type f | wc -l | awk '{print "  " $1 " files"}'
sync
for _ in 1 2 3 4 5; do hdiutil detach "$DEV" >/dev/null 2>&1 && DEV= && break; sleep 1; done
[ -z "$DEV" ] || { echo "detach failed: $OUT"; exit 1; }
echo "OK: $OUT"
