#!/usr/bin/env bash
# Ciclone - build libsd2snesfw.a: the sd2snes firmware compiled for the HOST.
#
# How the HAL is swapped without editing extern/: shadow headers in hal_host/
# win by -I order, but quoted #includes ("config.h", "spi.h", "timer.h", ...)
# resolve in the INCLUDER's own directory FIRST. The firmware .c live in src/
# next to the real config.h/spi.h/timer.h, so compiling them in place would pull
# the real headers. We therefore STAGE byte-exact copies of each firmware .c into
# build/fw_src/ (same trick as extern/.../tests/host/run.sh) and compile those,
# leaving everything in extern/ untouched. The .c stay verbatim; only headers and
# the lpc175x/usb/fpga/printf .c are replaced.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/extern/sd2snes/src"
HAL="$ROOT/hal_host"
INC="$ROOT/include"
FPGA="$ROOT/fpga_model"
BUILD="$ROOT/build"
STAGE="$BUILD/fw_src"
OBJ="$BUILD/obj"

CC="${CC:-clang}"
CXX="${CXX:-clang++}"
# -I order: hal_host (shadows) -> include (seam) -> src (real headers).
CFLAGS="-std=gnu99 -O1 -g -fno-strict-aliasing -Wno-implicit-function-declaration"
CFLAGS="$CFLAGS -Wno-int-conversion -Wno-incompatible-pointer-types"
# Evita colisao com a API libsnes (snes_init/snes_reset existem nos dois): renomeia
# as funcoes de controle do console do firmware. Token-based, nao afeta snes_reset_loop/_pulse.
CFLAGS="$CFLAGS -Dsnes_init=fw_snes_init -Dsnes_reset=fw_snes_reset"
# -I order: hal_host (shadows) -> include (seam) -> src -> src/lpc175x.
# lpc175x is LAST so hal_host/spi.h and hal_host/timer.h shadow lpc175x/spi.h
# and lpc175x/timer.h; the non-shadowed HAL headers (clock/led/power/rtc/
# sdnative/usbhw) still resolve there.
CPPFLAGS="-I $HAL -I $INC -I $SRC -I $SRC/lpc175x -I $SRC/include"
# Force-include the host config.h first in every TU so its shadow (and the real
# include-guard claims inside it) are set before any src/ header can pull the
# real config.h/bits.h via the includer-directory rule.
CPPFLAGS="$CPPFLAGS -include $HAL/config.h"
CXXFLAGS="-std=gnu++17 -O1 -g -I $INC -I $FPGA"

mkdir -p "$STAGE" "$OBJ"

# --- firmware .c compiled for the host (the REAL menu+load logic) ----------
# Everything except: lpc175x/* (HAL), usb*.c (USB stack), fpga.c (GPIO bit-bang),
# printf.c (clashes with libc stdio). Those are replaced by hal_host/*.
FW_SRCS=(
  main.c menucmd.c
  snes.c memory.c smc.c psram_io.c
  fpga_spi.c
  fileops.c ff.c ccsbcs.c strutil.c
  filetypes.c sort.c
  cfg.c cheat.c cheatcode.c cheatedit.c yaml.c yamlw.c savestate.c sgb.c hwinfo.c gameinfo.c
  patch.c patch_copier.c patchmeta.c crc32.c crc16.c rle.c
  cic.c cover.c theme.c msu1.c sysinfo.c pcmplay.c memtest.c manual.c igmenu.c trainer.c
  sufami.c spc7110rtc.c nes.c nes_chr.c sms.c atari.c gbc.c wdiag.c
  usbinterface.c
)
# M2.5: usbinterface.c (servidor FxPakPro REAL) entra no build. CDC_block_send/init
# (o transporte) ficam INDEFINIDOS aqui de propósito - o host os provê: host_runner
# (stub, USB desligado) ou o cdc_pty.c/teste FxPak (PTY/captura).
# Dropped from the firmware build (replaced by stubs / out of scope), documented:
#   fpga.c    -> hal_host/fpga_host.c  (GPIO bitstream load -> model reconfigure)
#   printf.c  -> libc stdio            (its printf/snprintf clash with libc)
#   cli.c     -> hal_host/misc_stubs.c (serial CLI; getline clashes with libc)
#   ymodem.c  -> dropped               (only used by cli.c; serial fw-update)
#   lpc175x/* -> hal_host/hal_stubs.c  (clock/uart/power/led/timer/spi/rtc/sdnative)
#   usb*.c    -> hal_host/usb_stubs.c  (USB/CDC stack; FxPakPro-over-socket is M2.5)

OBJS=()
echo "== staging + compiling firmware sources (host) =="
for f in "${FW_SRCS[@]}"; do
  base="$(basename "$f")"
  # skip sources absent in this checkout (older firmware trees lack some of them)
  # -- keeps the host build tree-agnostic.
  [ -f "$SRC/$f" ] || { echo "  skip (not in this repo): $f"; continue; }
  # main.c: rename main -> ciclone_fw_main so it's callable as a function.
  if [ "$base" = "main.c" ]; then
    extra="-Dmain=ciclone_fw_main"
  else
    extra=""
  fi
  cp "$SRC/$f" "$STAGE/$base"
  o="$OBJ/fw_$(echo "$base" | sed 's/\.c$/.o/')"
  # shellcheck disable=SC2086
  $CC $CFLAGS $CPPFLAGS $extra -c "$STAGE/$base" -o "$o"
  OBJS+=("$o")
done

# --- host HAL / shims (C) ---------------------------------------------------
echo "== compiling hal_host shims (C) =="
HAL_C=( hal_stubs.c rtc_host.c usb_stubs.c misc_stubs.c fpga_host.c diskio.c sd_image.c )
for f in "${HAL_C[@]}"; do
  o="$OBJ/hal_$(echo "$f" | sed 's/\.c$/.o/')"
  # shellcheck disable=SC2086
  $CC $CFLAGS $CPPFLAGS -c "$HAL/$f" -o "$o"
  OBJS+=("$o")
done

# --- C++ glue (reconfigure -> model) ---------------------------------------
echo "== compiling C++ glue =="
# shellcheck disable=SC2086
$CXX $CXXFLAGS -c "$HAL/fpga_reconf_glue.cpp" -o "$OBJ/hal_fpga_reconf_glue.o"
OBJS+=("$OBJ/hal_fpga_reconf_glue.o")

# --- archive ----------------------------------------------------------------
echo "== archiving libsd2snesfw.a =="
rm -f "$BUILD/libsd2snesfw.a"
ar rcs "$BUILD/libsd2snesfw.a" "${OBJS[@]}"
ranlib "$BUILD/libsd2snesfw.a" 2>/dev/null || true

echo ""
echo "OK: $BUILD/libsd2snesfw.a"
ls -la "$BUILD/libsd2snesfw.a"
