#!/usr/bin/env bash
# Recria build/sdcard.img se ele não existe ou se o menu mais recente (tools/menu_dir.sh) não é o
# que está dentro dele (carimbo build/sdcard.img.menu, gravado pelo make_sdimg.sh) -- a janela
# nunca abre com um m3nu.bin velho. Um jogo posto com run/sd.sh continua lá enquanto o menu não mudar.
set -e
cd "$(dirname "$0")/.."
IMG=build/sdcard.img
D="$(bash tools/menu_dir.sh)"
want="$(shasum "$D/m3nu.bin" "$D/igmenu.bin" 2>/dev/null | awk '{print $1}')"
if [ ! -f "$IMG" ] || [ "$want" != "$(cat "$IMG.menu" 2>/dev/null)" ]; then
  bash tools/make_sdimg.sh
fi
