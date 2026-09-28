#!/usr/bin/env bash
# CENÁRIO: builda + testa TODA a pilha (M0-M4). É o "CI". Deve terminar em "== TUDO OK ==".
set -e
cd "$(dirname "$0")/.."
bash tools/build_all.sh
