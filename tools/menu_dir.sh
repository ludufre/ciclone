#!/usr/bin/env bash
# Imprime a pasta do menu mais recente: o bin/ do seu build da firmware ou o build/menu/ do
# tools/build_menu.sh -- o que tiver o m3nu.bin mais novo. Sem nenhum, imprime o bin/.
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
best="$ROOT/extern/sd2snes/bin"; best_t=0
for d in "$ROOT/extern/sd2snes/bin" "$ROOT/build/menu"; do
  [ -f "$d/m3nu.bin" ] || continue
  t=$(stat -f %m "$d/m3nu.bin")
  if [ "$t" -gt "$best_t" ]; then best="$d"; best_t=$t; fi
done
echo "$best"
