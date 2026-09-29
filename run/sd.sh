#!/usr/bin/env bash
# CENÁRIO: (re)criar a imagem do SD. Opcional: passe um .sfc/.smc p/ adicioná-lo à imagem.
#   bash run/sd.sh                 -> só o menu (/sd2snes/m3nu.bin)
#   bash run/sd.sh ~/roms/jogo.sfc -> menu + o jogo (testar carga de ROM)
set -e
cd "$(dirname "$0")/.."
bash tools/make_sdimg.sh
if [ -n "${1:-}" ]; then
  [ -f "$1" ] || { echo "arquivo nao encontrado: $1"; exit 1; }
  echo "== adicionando $(basename "$1") à imagem =="
  # mount point from attach's own output, as in tools/make_sdimg.sh (not `df | grep`)
  ATTACH="$(hdiutil attach -nobrowse build/sdcard.img 2>/dev/null | tail -1)"
  DEV="$(printf '%s\n' "$ATTACH" | awk '{print $1}')"
  MNT="$(printf '%s\n' "$ATTACH" | awk -F'\t' '{print $NF}')"
  [ -n "$DEV" ] && [ -d "$MNT" ] || { echo "falha ao montar"; exit 1; }
  COPYFILE_DISABLE=1 cp -X "$1" "$MNT/"
  find "$MNT" -name '._*' -delete 2>/dev/null || true
  sync; hdiutil detach "$DEV" >/dev/null
  echo "OK: $(basename "$1") adicionado (rode bash run/menu.sh p/ navegar até ele)"
fi
