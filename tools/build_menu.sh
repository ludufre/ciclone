#!/usr/bin/env bash
# Ciclone - builda o MENU do working tree do sd2snes num host de build (SSH) e traz o pacote
# que os testes usam: m3nu.bin + igmenu.bin + os .map de símbolos (data.map = variáveis WRAM do
# menu). O harness precisa do .map do MESMO build do m3nu.bin -- por isso este script, que não
# mexe no bin/ da firmware. O host precisa do toolchain do menu (snescom/sneslink, python3).
#   bash tools/build_menu.sh [destino]              (default build/menu, working tree)
#   REF=HEAD bash tools/build_menu.sh build/menu-head   (um commit/branch, via git archive --
#                                                      o working tree não é tocado)
# Config (env ou .ciclone.env): SERVER (obrigatório, user@host do build), SERVER_DIR (pasta de
# trabalho no host; default ciclone-menu, relativa ao HOME de lá).
set -euo pipefail
cd "$(dirname "$0")/.."
. tools/env.sh
SERVER="${SERVER:?defina SERVER=user@host (host de build com snescom/sneslink), no env ou no .ciclone.env}"
SERVER_DIR="${SERVER_DIR:-ciclone-menu}"
DEST="${1:-build/menu}"
SRC="extern/sd2snes"
[ -d "$SRC/snes" ] || { echo "sem $SRC/snes (rode tools/setup.sh)"; exit 1; }
REPO="$SRC"
if [ -n "${REF:-}" ]; then
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  git -C "$REPO" archive "$REF" src snes | tar -x -C "$TMP"
  SRC="$TMP"
fi
rsync -a --delete --exclude '*.o65' --exclude '*.map' --exclude 'obj-*' "$SRC/src" "$SRC/snes" "$SERVER:$SERVER_DIR/"
ssh "$SERVER" "cd $SERVER_DIR && make -C snes clean >/dev/null 2>&1; make -C snes >/tmp/ciclone-menu.log 2>&1 || { tail -30 /tmp/ciclone-menu.log; exit 1; }"
mkdir -p "$DEST"
rm -f "$DEST"/*.map
scp -q "$SERVER:$SERVER_DIR/snes/m3nu.bin" "$SERVER:$SERVER_DIR/snes/igmenu.bin" "$DEST/"
scp -q "$SERVER:$SERVER_DIR/snes/*.map" "$DEST/"
git -C "$REPO" rev-parse --short "${REF:-HEAD}" > "$DEST/REV" 2>/dev/null || true
[ -n "${REF:-}" ] || git -C "$REPO" diff --quiet -- src snes 2>/dev/null || echo "+dirty" >> "$DEST/REV"
echo "OK: $DEST ($(tr '\n' ' ' < "$DEST/REV")) -> $(ls "$DEST" | wc -l | tr -d ' ') arquivos"
