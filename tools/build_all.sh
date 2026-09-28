#!/usr/bin/env bash
# Ciclone - build + teste de TODA a pilha verificada, em um comando.
# Rode da raiz do ciclone:  bash tools/build_all.sh
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
BSNES="$ROOT/extern/bsnes-plus/bsnes"
VINC="$(verilator --getenv VERILATOR_ROOT 2>/dev/null)/include"
mkdir -p build
echo "== [0/7] symlinks de extern/ =="; [ -e extern/sd2snes ] || bash tools/setup.sh

echo "== [1/7] libsnes (core do bsnes + chip sd2snes) =="
( cd "$BSNES" && make platform=osx profile=compatibility library >/dev/null )

echo "== [2/7] teste do FpgaModel comportamental (ASan) =="
clang++ -std=gnu++17 -O1 -g -fsanitize=address,undefined -I include -I fpga_model \
  fpga_model/behavioral.cpp tests/test_fpga_model.cpp -o build/test_fpga_model
build/test_fpga_model >/dev/null && echo "   OK: test_fpga_model"

echo "== [3/7] firmware host: libsd2snesfw.a =="
bash firmware_lib/build.sh >/dev/null && echo "   OK: build/libsd2snesfw.a"

echo "== [4/7] host_runner (M1 raw + M2.C --sd2snes + M2 --fw) =="
clang++ -std=gnu++17 -O2 -I include -I fpga_model -I "$BSNES/snes/libsnes" \
  host_runner/runner.cpp fpga_model/behavioral.cpp \
  build/libsd2snesfw.a "$BSNES/out/libsnes.a" -o build/host_runner_fw -lpthread
echo "   OK: build/host_runner_fw"

echo "== [5/7] M1: menu boota (emu_mode), captura frame =="
M1_MENU=extern/sd2snes/bin/m3nu.bin; [ -f "$M1_MENU" ] || M1_MENU=build/menu/m3nu.bin
build/host_runner_fw "$M1_MENU" build/frame.ppm 240 >/dev/null 2>&1
python3 tools/ppm2png.py build/frame.ppm build/frame.png >/dev/null && echo "   OK: build/frame.png"

echo "== [6/7] M2: firmware REAL dirige o menu (--fw) =="
[ -f build/sdcard.img ] || bash tools/make_sdimg.sh >/dev/null 2>&1 || true
build/host_runner_fw --fw build/sdcard.img build/frame_fw.ppm 180 > build/frame_fw.log 2>&1
python3 tools/ppm2png.py build/frame_fw.ppm build/frame_fw.png >/dev/null && echo "   OK: build/frame_fw.png"

echo "== [7/9] M3: FPGA Verilated lado-MCU (TEST + round-trip de memória) =="
bash fpga_model/verilate.sh >/dev/null 2>&1
clang++ -std=gnu++17 -O2 -I build/vfpga -I "$VINC" -I "$VINC/vltstd" \
  tests/test_vfpga_spi.cpp build/vfpga/Vmain__ALL.a build/vfpga/verilated.o build/vfpga/verilated_threads.o \
  -o build/test_vfpga_spi
build/test_vfpga_spi >/dev/null && echo "   OK: test_vfpga_spi"

echo "== [8/9] M3: FPGA Verilated both-sides (sim_top: MCU escreve, SNES lê) =="
bash fpga_model/verilate_sim.sh >/dev/null 2>&1
clang++ -std=gnu++17 -O2 -I build/vfpga_sim -I "$VINC" -I "$VINC/vltstd" \
  tests/test_vfpga_sim.cpp build/vfpga_sim/Vsim_top__ALL.a build/vfpga_sim/verilated.o build/vfpga_sim/verilated_threads.o \
  -o build/test_vfpga_sim
build/test_vfpga_sim >/dev/null && echo "   OK: test_vfpga_sim"

echo "== [9/9] M2.5: servidor FxPakPro REAL (INFO) - direto + sobre PTY =="
clang++ -std=gnu++17 -O1 -g -I include -I fpga_model \
  tests/test_fxpak_info.cpp build/libsd2snesfw.a fpga_model/behavioral.cpp -o build/test_fxpak_info -lpthread
build/test_fxpak_info >/dev/null && echo "   OK: test_fxpak_info (INFO direto)"
clang -std=gnu99 -O1 -g -I hal_host -I include -I extern/sd2snes/src -c hal_host/cdc_pty.c -o build/obj/hal_cdc_pty.o
clang++ -std=gnu++17 -O1 -g -I include -I fpga_model \
  tests/test_fxpak_pty.cpp build/obj/hal_cdc_pty.o build/libsd2snesfw.a fpga_model/behavioral.cpp -o build/test_fxpak_pty -lpthread
build/test_fxpak_pty >/dev/null && echo "   OK: test_fxpak_pty (FxPakPro sobre PTY serial)"

if [ -f /opt/homebrew/include/unicorn/unicorn.h ]; then
  echo "== [+] M4: .im3 REAL boota no emulador LPC1756 (Unicorn) + FpgaModel via seam SPI =="
  bash m4_unicorn/build.sh >/dev/null 2>&1
  # o par .im3+.elf do MESMO build vem do servidor (o build local só traz o .im3)
  [ -f build/m4fw/sd2snes-intermediate.elf ] || bash tools/fetch_m4fw.sh >/dev/null 2>&1 || true
  IM3=build/m4fw/firmware.im3
  if build/lpc_emu "$IM3" 2>/dev/null | grep -q "menu_main_loop ALCANCADO"; then
    echo "   OK: firmware REAL bootou ('SNES GO!', sram test ok) e alcançou o command loop"
  else
    echo "   AVISO: M4 não alcançou o command loop (rode tools/fetch_m4fw.sh: precisa do .im3 + .elf do mesmo build)"
  fi
else
  echo "== [+] M4: pulado (instale unicorn: brew install unicorn) =="
fi

echo ""
echo "== TUDO OK =="
echo "  M1  -> build/frame.png      (menu emu_mode, headless)"
echo "  M2  -> build/frame_fw.png   (menu em boot normal, dirigido pelo firmware REAL)"
echo "  M3  -> test_vfpga_spi (lado-MCU) + test_vfpga_sim (both-sides: MCU escreve, SNES lê via RTL real)"
echo "  M2.5-> test_fxpak_info + test_fxpak_pty (servidor FxPakPro REAL responde INFO, sobre PTY serial)"
echo "  M4  -> build/lpc_emu (.im3 REAL boota no emulador LPC1756: 'SNES GO!' + menu_main_loop, FpgaModel via SPI)"
