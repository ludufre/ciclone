#!/usr/bin/env bash
# CENÁRIO: primeira vez - instala dependências (Homebrew) e cria os symlinks de extern/.
set -e
cd "$(dirname "$0")/.."
echo "== instalando dependências (brew) =="
brew install qt@5 verilator unicorn sdl2 || true
echo "== symlinks de extern/ =="
bash tools/setup.sh
echo
echo "Pronto. Agora: bash run/test.sh  (builda + testa tudo)  ou  bash run/menu.sh  (abre o menu)"
