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
  DEV="$(hdiutil attach build/sdcard.img | head -1 | awk '{print $1}')"
  MNT="$(df 2>/dev/null | grep "$DEV" | awk '{print $NF}' | head -1)"
  [ -n "$MNT" ] || { echo "falha ao montar"; exit 1; }
  cp "$1" "$MNT/"
  sync; hdiutil detach "$DEV" >/dev/null
  echo "OK: $(basename "$1") adicionado (rode bash run/menu.sh p/ navegar até ele)"
fi
