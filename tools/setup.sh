#!/usr/bin/env bash
# Prepara extern/ (gitignored).
#   - bsnes-plus: CLONADO na branch com o chip sd2snes (ludufre/bsnes-plus @ ciclone-sd2snes-chip).
#   - sd2snes:    a árvore da firmware (a pasta com src/, snes/ e verilog/). Com SD2SNES_DIR, vira
#                 symlink para esse checkout (o seu, onde você edita); sem ele, clona o fork público.
#                 Os binários do menu (bin/m3nu.bin, bin/igmenu.bin) NÃO estão no git: vêm do seu
#                 build da firmware ou do tools/build_menu.sh (build/menu/).
# Overrides por env (ou no .ciclone.env da raiz, fora do git): SD2SNES_DIR, SD2SNES_URL,
# BSNES_URL, BSNES_BRANCH.
set -e
cd "$(dirname "$0")/.."
. tools/env.sh
SD2SNES_URL="${SD2SNES_URL:-https://github.com/ludufre/sd2snes.git}"
BSNES_URL="${BSNES_URL:-https://github.com/ludufre/bsnes-plus.git}"
BSNES_BRANCH="${BSNES_BRANCH:-ciclone-sd2snes-chip}"
mkdir -p extern

# --- bsnes-plus: clone na branch do chip (idempotente) ---
[ -L extern/bsnes-plus ] && rm -f extern/bsnes-plus          # tira symlink antigo (não toca no alvo)
if [ -d extern/bsnes-plus/.git ]; then
  echo "bsnes-plus: atualizando p/ $BSNES_BRANCH"
  git -C extern/bsnes-plus fetch --quiet origin "$BSNES_BRANCH"
  git -C extern/bsnes-plus checkout --quiet "$BSNES_BRANCH"
  git -C extern/bsnes-plus pull --quiet --ff-only origin "$BSNES_BRANCH" || true
else
  echo "bsnes-plus: clonando $BSNES_URL @ $BSNES_BRANCH"
  git clone --quiet --branch "$BSNES_BRANCH" "$BSNES_URL" extern/bsnes-plus
fi

# --- sd2snes: symlink p/ o seu checkout, ou clone do fork público ---
if [ -n "${SD2SNES_DIR:-}" ]; then
  [ -f "$SD2SNES_DIR/src/main.c" ] || { echo "SD2SNES_DIR=$SD2SNES_DIR não parece a árvore da firmware (sem src/main.c)"; exit 1; }
  [ -L extern/sd2snes ] || [ ! -e extern/sd2snes ] || { echo "extern/sd2snes existe e não é symlink; remova-o para trocar"; exit 1; }
  ln -sfn "$SD2SNES_DIR" extern/sd2snes
  echo "sd2snes: symlink -> $SD2SNES_DIR"
elif [ ! -e extern/sd2snes ]; then
  echo "sd2snes: clonando $SD2SNES_URL"
  git clone --quiet "$SD2SNES_URL" extern/sd2snes
else
  echo "sd2snes: mantendo extern/sd2snes"
fi

echo "extern/ pronto."
