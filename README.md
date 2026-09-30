# Ciclone

**English** | [Português](README-BR.md)

Emulation / co-simulation environment for the **sd2snes+ firmware** - develop and test the firmware
(SNES menu in 65816 asm + LPC1756 MCU in C + Cyclone IV FPGA in Verilog) **on a PC, with no physical hardware**.

The goal: you edit the firmware, run it on the PC, **see the menu in a window and navigate with the
keyboard** - no cartridge flashing, no SNES needed.

---

## Table of contents

- [The idea](#the-idea)
- [Prerequisites](#prerequisites-macos)
- [Quick start](#quick-start)
- [Ready-made commands (`run/`)](#ready-made-commands-run)
- [How to open it (see the menu)](#how-to-open-it-see-the-menu)
- [How to test](#how-to-test)
- [Development lifecycle](#development-lifecycle)
- [The SD image](#the-sd-image)
- [Local configuration](#local-configuration)
- [Command reference](#command-reference)
- [Project layout](#project-layout)
- [Milestone status](#milestone-status)
- [Gotchas / troubleshooting](#gotchas--troubleshooting)
- [Licenses & credits](#licenses--credits)

---

## The idea

The firmware is really **3 asynchronous processors** that talk through the SNESCMD buffer (a dual-port
BRAM in the FPGA, exposed to the SNES at `$2A00`):

```
  bsnes-plus (SNES 65816)  -->  "sd2snes" chip  -->  FPGA model  <--SPI--  MCU firmware
   runs m3nu.bin                 (in bsnes)        (seam #2)     (seam #1)  (libsd2snesfw / .im3)
```

Two **pluggable seams** swap fidelity without rewriting anything:

- **Seam #1 - SPI transport:** (A) firmware as an **in-process lib** (fast); (B) the **real `.im3`** on a
  Cortex-M3 emulator (fidelity).
- **Seam #2 - FPGA model:** (A) **behavioral** C++ (fast); (B) **Verilated `main.v`** (real RTL).

The **A/A** pair gives the fast dev loop; **B/B** gives maximum fidelity. Both sides use the **same**
`FpgaModel` and the **same** SPI seam (`ciclone_spi_txrx/select/deselect`).

---

## Prerequisites (macOS)

```sh
brew install qt@5 verilator unicorn sdl2
```

| Tool | What for | Required? |
|---|---|---|
| `clang` + `make` (Xcode CLT) | everything | yes |
| `qt@5` | build the bsnes-plus core | yes |
| `unicorn` | M4 - LPC1756 emulator that runs the real `.im3` | for M4 |
| `sdl2` | interactive window (`--gui`) | for the window |
| `verilator` | M3 - Verilated FPGA (real RTL) | for M3 |
| `python3` | convert frame PPM->PNG | for screenshots |

> You **don't need** `arm-none-eabi-gcc` or `snescom` on the Mac for the C side: the firmware C is
> compiled natively by `firmware_lib/build.sh`. The **menu** (`m3nu.bin`/`igmenu.bin`, 65816 asm) and the
> real `.im3` come from a firmware build: either your own (they land in the firmware tree's `bin/`) or a
> build host reached over SSH (`tools/build_menu.sh`, `tools/fetch_m4fw.sh`; see
> [Local configuration](#local-configuration)).

---

## Quick start

```sh
bash tools/setup.sh        # 1. clone bsnes-plus (chip branch) + the sd2snes firmware tree
                           #    (SD2SNES_DIR=/path/to/your/sd2snes symlinks your own checkout instead)
bash tools/build_menu.sh   # 2. menu binaries + symbol maps (needs a build host, see Local configuration;
                           #    skip it if your firmware tree already has bin/m3nu.bin)
bash tools/build_all.sh    # 3. build + test EVERYTHING (M0-M4). Should end with "== TUDO OK =="
bash tools/make_sdimg.sh   # 4. create build/sdcard.img (FAT32 with the menu + a test tree)
```

Then, to **see the menu in a window**: `bash run/menu.sh`.

---

## Ready-made commands (`run/`)

One script per scenario - each one builds whatever is missing on its own:

| Command | Scenario |
|---|---|
| `bash run/setup.sh` | first time: install deps (brew) + prepare `extern/` (bsnes-plus + the firmware tree) |
| `bash run/test.sh` | build + test **everything** (M0-M4) |
| `bash run/menu.sh` | **open the menu in a window** (real firmware) - navigate with the keyboard |
| `bash run/firmware.sh [im3]` | boot the **real `.im3`** in the emulator and show the firmware log |
| `bash run/dev.sh` | dev loop: recompile the C firmware and **reopen the window** |
| `bash run/screenshot.sh [frames]` | generate and open a screenshot of the menu (headless) |
| `bash run/sd.sh [game.sfc]` | (re)create the SD image; optionally add a game |
| `bash run/keys.sh "<buttons>" "<shots>"` | headless button script -> PNGs in `build/shots/` |
| `bash run/test_menu.sh [-k filter]` | **automated menu suite** (builds the working-tree menu and runs it) |

---

## How to open it (see the menu)

### Interactive window (recommended)

It's the **bsnes-plus core (libsnes) in an SDL window**, with the sd2snes chip + the **REAL firmware** in a
thread + the FpgaModel. You actually navigate the menu.

```sh
bash host_runner/build_gui.sh                       # builds build/host_runner_gui (needs sdl2)
build/host_runner_gui --gui build/sdcard.img
```

**Controls:**

| Key | SNES | | Key | SNES |
|---|---|---|---|---|
| Arrows | D-pad | | Enter | Start |
| `Z` / `X` | B / A | | Shift | Select |
| `A` / `S` | Y / X | | `Q` / `W` | L / R |
| `M` | in-game menu | | `ESC` | quit |

`M` presses the in-game menu combo for you (the one the firmware armed for the loaded game - default
L+R+Y+Left, or your `IngameButtonsMenu`): four keys at once often do not register on a keyboard. It holds
the combo for 20 frames and releases it; the game sees those buttons too, as it would on a pad. Hooks are
held off for 10 s after a game starts, as on the cart.

> This is not the full bsnes-plus Qt app (with its UI menus/debugger) - it's its **emulation engine** in a
> window, with the real firmware. It reuses 100% of the tested `--fw` wiring.

### Screenshots (headless, no window)

```sh
open build/frame.png       # menu alone (emu_mode fallback) - produced by build_all
open build/frame_fw.png    # menu driven by the real firmware  - produced by build_all
```

To generate a one-off frame:

```sh
build/host_runner_fw --fw build/sdcard.img build/out.ppm 180
python3 tools/ppm2png.py build/out.ppm build/out.png && open build/out.png
```

### Button scripts (headless)

`host_runner_fw` takes an input script and several captures in one run - reproduce a menu bug without a
window and compare two `m3nu.bin`:

```sh
# Y on an MSU-1 folder: down 1, press Y, capture before and after
bash run/keys.sh "120:DOWN,160:Y" "150:before,260:after"
# straight to the runner: --keys "F:BTN[+BTN][:HOLD],..."  --shots "F:out.ppm,..."
build/host_runner_fw --fw --keys "120:DOWN,160:Y,280:B" --shots "260:a.ppm,400:b.ppm" build/sdcard.img last.ppm 401
```

Buttons: `B Y SEL START UP DOWN LEFT RIGHT A X L R`, and `MENU` for the armed in-game menu combo (combine
with `+`; `HOLD` in frames, default 4 - 20 for `MENU`). The
firmware log (printf) goes to the runner's stdout.

### Automated menu tests

`tests/menu/` drives the **REAL menu + REAL firmware** and asserts on **state**, not pixels: screen text
(decoded from the WRAM tilemap buffers), menu variables (via the `data.map` of the same build), shared
PSRAM/BSRAM, the firmware log and the card files after the run.

```sh
bash run/test_menu.sh                  # builds the working-tree menu on the build host (~15 s) and runs all
bash run/test_menu.sh -k msu -v        # filter + log
NO_BUILD=1 bash run/test_menu.sh       # reuse build/menu
REF=HEAD bash run/test_menu.sh         # test the MENU of a commit (git archive; the C firmware stays the working tree)
```

A test is a `test_*(t)` function in `tests/menu/test_*.py`; the API lives in `tests/menu/ciclone.py`
(`press/wait/settle`, `screen/has/selected/goto`, `u8/u16(symbol)`, `psram`, `fwlog`, `t.sd(config=,
extra=)`, `t.read`, `c.tr(label, lang)`). Failures leave `screen*.txt/png`, `fw.log` and the traceback in
`build/menu-tests/<test>/`. Current coverage: 23 tests (~10 s): browser, MSU-1 folders, context menu
(incl. Y on an MSU-1 folder), game load (missing-core popup, boot +
Recents), Favorites/Recents lists and all 8 languages. A regression test is only useful if it fails
without the fix: `REF=<commit before the fix>` shows it. The suite needs the symbol maps of the menu under test, which is why it builds the menu
itself (`tools/build_menu.sh`) instead of using a release `m3nu.bin`.

**Real games** (`tests/menu/test_games.py`): Super Mario World (LoROM) and Donkey Kong Country 3 (HiROM,
4 MB) are loaded through the menu and played on the FPGA model's mappers, asserting on the game's own WRAM
state (game mode, Mario moving; DKC3 down to the world map) - and the **in-game menu** over SMW: the
combo (L+R+Y+Left) opens it, R changes tab, B closes it and Mario walks again. That path is all real code
(the firmware's NMI stub at `$2A10`, the savestate handler, `igmenu.bin`); what makes it work is the FPGA
model reproducing `cheat.v`: the interrupt vector hijack, the SNESCMD unlock with the `$C0-$FF` linear
window, the patched branch operands, the release on the hook's final `jmp ($FFxx)`, the reset hook
(`$2A7D`), the 10 s holdoff, plus the `ctx.v` register shadows the menu restores on close. The bsnes chip
feeds it what the cart edge sees outside its own ranges (vector fetch, bus writes, `$4016` reads, /RESET).
The same machinery runs the rest of the in-game features, each with a test: **savestates** (Start+R saves
- the handler freezes the game in the hook, the FPGA copier (`dma.v`, `$2020-$2029` or MCU `$D4`) stages
the WRAM mirror, VRAM/CGRAM/OAM are read back and the MCU writes the 320 KB image to the card; Start+L
replays it; the card carries the firmware tree's `savestate/savestate_fixes.yml`, whose SMW entry re-uploads
the music bank of the loaded area - the APU is not in a state, and SMW swaps banks between levels and the
overworld), the **gestures** the stub echoes to the MCU (L+R+Start+Select resets the game, L+R+Select+X
goes back to the menu, L+R+Start+A/B cheats on/off, L+R+Start+Y / +X hooks off / off for 10 s), **WRAM
cheats** (patch code the stub runs every NMI) and **ROM cheats** (served by the FPGA on read). The IRQ hook
(for IRQ-only frame loops) and the USB exe hook (`$2C00`) are covered by `tests/test_fpga_model.cpp` only.
ROMs never go into the repo: point
`CICLONE_ROMS=<folder>` at your dumps (searched recursively, matched by No-Intro CRC32); without it, or
without a matching dump, those tests report as skipped, not failed.

Timing fidelity: `CICLONE_SYNC=0` turns off command sync (while the MCU handles a command, SNES accesses
to `$2A00-$2FFF` wait for it to get back to polling - on hardware the MCU always wins that race; without
it, 1 in 12 deletes lost the following READDIR even at real time), `CICLONE_SPEED` (default 4x real time
in `--serve`, paced by the SNES beam clock), `CICLONE_TRACE_CMD=<file>` (timestamped MCU_CMD/SNES_CMD
trace from both sides), `CICLONE_FIXED_TIME` (frozen clock), `CICLONE_TRACE_APU=<file>` /
`CICLONE_AUDIO_LEVEL=<file>` (APU port writes with PC and stack / sound level per frame - see below).

### Writing a savestate audio fix

A state carries WRAM, VRAM and the registers, never the APU: after a load the game believes its sound
CPU is in the state it had at the save, and it is not. `savestate_fixes.yml` (firmware tree, copied onto
every card) patches that per game, keyed by the ROM header checksum, with code the savestate handler runs
after every save and load. Most entries copy one byte (a WRAM echo counter <- the live `$214x` port); some
games need code. `tools/ssfix/smw_a0da.s` (Super Mario World: re-upload the music bank of the loaded
area) and `tools/ssfix/dkc3_b28c.s` / `dkc2_1202.s` / `dkc1_ef80.s` (Donkey Kong Country 3/2/1: replay the loaded
scene's song) were found
and verified with the tools below - the same loop works for any game:

1. **Reproduce and trace.** Run the case with the APU ports traced and the sound level logged:
   `CICLONE_TRACE_APU=build/apu.log CICLONE_AUDIO_LEVEL=build/level.log bash run/menu.sh` (or `env=`
   on `t.menu()` / `_play()` in a test). The level log is `<frame> <rms>` per frame: 0 = silence.
2. **Read what the game says to the APU:** `python3 tools/apu_trace.py build/apu.log --from F --callers`.
   Uploads (IPL transfers of the driver, samples or a song bank) are folded into one line; the other lines
   are commands (song requests, sound effects, pause, handshakes) with the PC that wrote them.
3. **Find the routine to call again.** The upload lines and `--callers` list the JSRs found on the stack
   (candidates - check them in the ROM): the routine that picks and uploads the right bank, and who calls
   it on each area change. Then find where the game keeps the song it asks for (a request byte its NMI
   copies to a port, a "current song" variable, a table indexed by map/level).
4. **Write the fix** as a `tools/ssfix/<game>_<chk>.s` source (header `; key:`, `; name:`, `;|` notes)
   and assemble it: `python3 tools/ss65.py tools/ssfix/<file>.s` prints the entry (split into 64-byte
   `@` items); paste it into the firmware tree's `savestate/savestate_fixes.yml`. Rules the SMW one
   follows: it runs after saves too, so test `CS_SA1_LOAD` (`$FE1013`, 1 = load) if it must act only
   on a load; it starts with A 8-bit / X 16-bit and unknown DBR/D - set what the game's code expects and
   restore them; stay position independent (`brl`/`per`), other entries may come first; a game routine
   that ends in `RTS` is reached from bank `$FE` through an RTL trampoline (`phk`, `per back-1`, `pea
   <a $6B byte in the routine's bank>-1`, `jml routine`). Inside the hook, banks `$C0-$FF` are the
   handler's PSRAM, not the game's ROM: a routine that reads its data there (HiROM games) cannot run
   from the fix - `tools/ssfix/dkc3_b28c.s` defers the call instead, planting a one-shot routine in
   free WRAM and pointing the game's NMI dispatch at it, so it runs on the first NMI after the hook.
5. **Prove it.** `m.aram()` + `Menu.bank_match()` compare the APU memory with two known snapshots (the
   bank of area A vs area B); write the test so it fails without the entry (`test_savestate_restores_the_
   music_bank` does - remove the entry and it reports 0% of the level bank back). `test_ssfix` keeps each
   `.s` and its `.yml` entry identical.

---

## How to test

### All at once (the "CI")

```sh
bash tools/build_all.sh
```

Builds and runs the whole verified stack. Expected output (abbreviated):

```
OK: test_fpga_model
OK: build/frame.png
OK: build/frame_fw.png
OK: test_vfpga_spi
OK: test_vfpga_sim
OK: test_fxpak_info (INFO direto)
OK: test_fxpak_pty (FxPakPro sobre PTY serial)
OK: firmware REAL bootou ('SNES GO!', sram test ok) e alcançou o command loop
== TUDO OK ==
```

### The REAL firmware booting in the emulator (M4)

```sh
bash m4_unicorn/build.sh
bash tools/fetch_m4fw.sh      # fetches build/m4fw/{firmware.im3, sd2snes-intermediate.elf} from the server
build/lpc_emu build/m4fw/firmware.im3
```

Shows the **real UART log** of the firmware up to the command loop. To see just the clean log:

```sh
build/lpc_emu build/m4fw/firmware.im3 2>&1 \
  | grep -vE "CIC toggle|syscon|i=[0-9]+ val="
```

A snippet of what you'll see:

```
sd2snes Mk.III
  [boot] f_mount (monta FAT do SD)
file_open (/sd2snes/m3nu.bin, 01): FR_OK(0)
file_open (/sd2snes/config.yml, 01): FR_OK(0)
SNES GO!
test sram
ok
  [boot] *** menu_main_loop ALCANCADO *** (firmware no command loop!)
```

(The harness's own log lines are in Portuguese.)

### Individual unit tests

```sh
build/test_fpga_model    # behavioral FpgaModel (9/9, under AddressSanitizer)
build/test_vfpga_spi     # Verilated FPGA, MCU side (TEST 0xf0->0xa5 + PSRAM round-trip)
build/test_vfpga_sim     # Verilated FPGA, both sides (MCU writes 0x42, SNES reads $C0:0010)
build/test_fxpak_info    # the REAL FxPakPro server answers an INFO
build/test_fxpak_pty     # FxPakPro over a serial port (PTY /dev/ttysNNN)
```

---

## Development lifecycle

### From your hardware flow to ciclone

The hardware loop is: **edit code -> build the firmware (`.im3` + `m3nu.bin`) -> copy it to the cartridge's
SD card -> test on a physical SNES.**

Ciclone **replaces the copy-to-SD + the physical SNES with the PC** for iteration. What you do depends on what
you edited:

#### Case 1 - you edited the C firmware (`src/*.c`), the common one

```sh
bash run/dev.sh
```

That's it. **No firmware build, no SD card, no SNES.** `run/dev.sh` recompiles the **same `src/*.c` you
edited** (`extern/sd2snes` is a symlink to your checkout when set up with `SD2SNES_DIR`) straight to the Mac
and reopens the window in seconds. You see the change in the menu right away.

> Why it's fast: the firmware becomes **native** Mac code (not emulated ARM) and is cached; only the harness
> recompiles. It tests the C **logic** - not the ARM binary nor the real drivers (see Case 2).

#### Case 2 - validate the REAL ARM binary (`.im3`)

```sh
# after your firmware build (arm-none-eabi-gcc, config-mk3):
bash tools/fetch_m4fw.sh      # or FW_OBJ_DIR=<firmware tree>/src/obj-mk3 for a local build
bash run/firmware.sh
```

Here you run your **normal firmware build** (the real `.im3` needs arm-gcc), but instead of the SD card +
SNES, `run/firmware.sh` **boots the `.im3` in the emulator** (Unicorn). Catches init/driver bugs
without flashing. The emulator resolves the `.elf` symbols at runtime, so it survives rebuilds (point it at
the new `.im3`; the `.elf` is auto-derived, or pass it explicitly: `bash run/firmware.sh <im3>`).

#### Case 3 - you edited the menu (65816 asm, `snes/`)

```sh
bash tools/build_menu.sh      # or your own firmware build (asm needs snescom)
bash run/sd.sh && bash run/menu.sh
```

The menu is asm, so `m3nu.bin` still comes from a real build. `run/sd.sh` puts the new `m3nu.bin` into the SD
image and `run/menu.sh` opens the window.

### Flow translation

| You edited | Today (hardware) | Now with ciclone |
|---|---|---|
| C firmware | build + SD card + SNES | **`bash run/dev.sh`** (seconds) |
| Validate the real `.im3` | build + SD card + SNES | build -> **`bash run/firmware.sh`** |
| Menu asm | build + SD card + SNES | `tools/build_menu.sh` -> **`bash run/sd.sh` -> `bash run/menu.sh`** (or `run/test_menu.sh`) |

### What still needs the real hardware

Ciclone is for **fast iteration**; the **final sign-off** is still a real build on a physical SNES. Because:

- **Case 1** tests the C **logic** (compiled for the Mac) - not the ARM binary nor the real drivers
  (SSP / native-SD / USB / timers are modeled or stubbed).
- **Case 2** tests the **real binary**, but with **modeled** peripherals, not the silicon.

In practice most loops happen in `run/dev.sh` / `run/test_menu.sh`; the hardware is for closing out.
Plain LoROM/HiROM games, the in-game menu, savestates, gestures and cheats run (see *Real games* above),
but not covered: coprocessor cores (and their savestate windows), the `ctx.v` WRAM/VRAM/APU mirrors (the
savestate overwrites what it takes from them with a read-back of the console, so only the APU image in
the state file is missing), hardware timing, audio.

---

## The SD image

`tools/make_sdimg.sh` creates `build/sdcard.img` (FAT32, 48 MB) with `/sd2snes/m3nu.bin` + `igmenu.bin`
(the menu the firmware loads: the NEWER of the firmware tree's `bin/` and `build/menu/`; the window
scripts rebuild the image by themselves when that menu changes), a dummy
`fpga_base.bi3`, and a **test tree** (`tools/sd_fixtures.py`): a loose ROM, an MSU-1 folder, a folder with
two ROMs and an empty folder. It uses macOS-native `hdiutil` - no mtools; the `._*` files macOS writes to
FAT are removed before unmounting. Its `config.yml` gets `ResetPatch: false` unless the given config names
the key, and the firmware tree's `savestate/savestate_inputs.yml` / `savestate_fixes.yml` go into
`/sd2snes/` like on a release card. With the reset patch on, the reset hook times an H-IRQ against `$4212` to catch a misaligned
CPU/PPU clock phase and resets until it passes - random on a console, a guaranteed fail on bsnes' fixed
timing, so every game would reset forever.

```sh
bash tools/make_sdimg.sh                       # creates build/sdcard.img
SIZE_MB=128 bash tools/make_sdimg.sh           # larger image
bash tools/make_sdimg.sh /path/custom.img      # another destination
M3NU=/path/m3nu.bin bash tools/make_sdimg.sh build/sd_fix.img   # another menu (e.g. a fix to compare)
SD_CONFIG=cfg.yml bash tools/make_sdimg.sh     # initial config.yml (e.g. ShowGameInfo: 2)
SD_FIXTURES=0 bash tools/make_sdimg.sh         # without the test tree (Test Game.sfc, MSU Game/, Two Games/, Empty Folder/)
```

**Add game ROMs** (to test ROM loading end-to-end): mount the image and copy `.sfc`/`.smc` files:

```sh
hdiutil attach build/sdcard.img                # mounts at /Volumes/SD2SNES
cp ~/roms/game.sfc /Volumes/SD2SNES/
hdiutil detach /Volumes/SD2SNES
```

Then, in the window, navigate to the game and press A - the real firmware does the load handshake.

---

## Local configuration

**Optional.** Without it, `tools/setup.sh` clones the public firmware fork and `tools/build_all.sh` runs as
long as the firmware tree has a built `bin/m3nu.bin`. You need it to test **your own checkout**, or to use a
**build host** for the menu + symbol maps (`tools/build_menu.sh`, which `run/test_menu.sh` calls) and for the
real `.im3` of M4 (`tools/fetch_m4fw.sh`).

Settings live in **`.ciclone.env`** at the repo root (git-ignored), read by `tools/setup.sh`,
`tools/build_menu.sh` and `tools/fetch_m4fw.sh`. An **environment variable always wins** over the file, so a
one-off override needs no edit: `FW_SERVER_DIR=/other/tree bash tools/fetch_m4fw.sh`.

Format: one `KEY=value` per line, `#` comments a whole line or the rest of one, **no quotes and no `~`/`$HOME` expansion** (the value is
taken literally, so use absolute paths).

```sh
# .ciclone.env
SD2SNES_DIR=/Users/me/src/sd2snes   # your firmware tree (the dir with src/, snes/, verilog/)
SERVER=me@buildhost                  # SSH build host with snescom/sneslink + python3 (menu) and the
                                     # firmware build (M4)
SERVER_DIR=ciclone-menu              # scratch dir on the host for tools/build_menu.sh (relative = its $HOME)
FW_SERVER_DIR=/home/me/sd2snes       # firmware tree on the host where the .im3 was built
```

| Variable | Used by | Default |
|---|---|---|
| `SD2SNES_DIR` | `setup.sh`: symlink `extern/sd2snes` to your checkout | clone `SD2SNES_URL` |
| `SD2SNES_URL` | `setup.sh` | `https://github.com/ludufre/sd2snes.git` |
| `BSNES_URL`, `BSNES_BRANCH` | `setup.sh` | `ludufre/bsnes-plus`, `ciclone-sd2snes-chip` |
| `SERVER` | `build_menu.sh`, `fetch_m4fw.sh` | none (they stop and say so) |
| `SERVER_DIR` | `build_menu.sh` | `ciclone-menu` |
| `FW_SERVER_DIR`, `OBJ` | `fetch_m4fw.sh` | none, `obj-mk3` |
| `FW_OBJ_DIR` | `fetch_m4fw.sh`: copy the `.im3` + `.elf` from a **local** build instead of SSH | unset |

The runner's own knobs (`CICLONE_SYNC`, `CICLONE_SPEED`, `CICLONE_TRACE_CMD`, `CICLONE_FIXED_TIME`,
`CICLONE_MENU`) are plain environment variables, not read from this file; see
[Automated menu tests](#automated-menu-tests).

---

## Command reference

| Command | What it does | Produces |
|---|---|---|
| `bash tools/setup.sh` | clone bsnes-plus (chip branch) + the firmware tree (or symlink `SD2SNES_DIR`) | `extern/*` |
| `bash tools/build_menu.sh` | build the menu of the firmware tree on the build host | `build/menu/` (bins + `.map`) |
| `bash tools/build_all.sh` | build + test M0-M4 | `build/*`, frames, tests |
| `bash tools/make_sdimg.sh` | create the FAT32 SD image | `build/sdcard.img` |
| `bash firmware_lib/build.sh` | REAL firmware -> host lib | `build/libsd2snesfw.a` |
| `bash host_runner/build_gui.sh` | interactive window (SDL) | `build/host_runner_gui` |
| `bash m4_unicorn/build.sh` | LPC1756 emulator (Unicorn) | `build/lpc_emu` |
| `bash fpga_model/verilate.sh` | Verilate `main.v` (MCU side) | `build/vfpga/` |
| `bash fpga_model/verilate_sim.sh` | Verilate `sim_top.v` (both sides) | `build/vfpga_sim/` |
| `build/host_runner_gui --gui build/sdcard.img` | **opens the menu window** | - |
| `build/host_runner_fw --fw build/sdcard.img out.ppm 180` | headless menu -> frame | `out.ppm` |
| `bash tools/fetch_m4fw.sh` | fetch the `.im3`+`.elf` pair from the build server | `build/m4fw/` |
| `build/lpc_emu build/m4fw/firmware.im3` | real `.im3` boots in the emulator | UART log |
| `bash run/keys.sh "<buttons>" "<shots>"` | headless button script | `build/shots/*.png` |
| `bash run/test_menu.sh [-k filter]` | automated menu suite | `build/menu-tests/` |
| `python3 tools/ppm2png.py in.ppm out.png` | PPM -> PNG | `out.png` |

---

## Project layout

| Dir | Contents |
|---|---|
| `extern/` | `bsnes-plus` **cloned** at branch `ciclone-sd2snes-chip` (has the sd2snes chip); `sd2snes` = the firmware tree (clone, or a **symlink** to your checkout) |
| `run/` | one script per scenario (window, dev loop, screenshots, button scripts, menu suite) |
| `host_runner/` | embeds the bsnes `libsnes`; headless (`--fw`) and window (`--gui`, SDL) modes |
| `fpga_model/` | `FpgaModel` interface + behavioral backend (`behavioral.cpp`) + Verilated (`sim/`, `stubs/`) |
| `firmware_lib/` | builds `libsd2snesfw.a` (a subset of the firmware's `src/*.c` for the host) |
| `hal_host/` | firmware HAL shims (clock/led/rtc/power/timer/uart/spi/diskio/usb/cdc_pty) |
| `m4_unicorn/` | LPC1756 (Cortex-M3) emulator that runs the real `.im3` + glue to the FpgaModel |
| `include/` | `ciclone_seam.h` - the C ABI of the SPI seam |
| `tests/` | tests (FpgaModel, Verilated SPI/sim, FxPak INFO/PTY, VCD trace); `tests/menu/` = the menu suite |
| `tools/` | `setup.sh`, `build_all.sh`, `build_menu.sh`, `make_sdimg.sh`, `sd_fixtures.py`, `fetch_m4fw.sh`, `ppm2png.py`, `ss65.py` + `ssfix/` (savestate fixes), `apu_trace.py` |
| `renode/` | (alternative M4) Renode scaffold + assessment - unused; Unicorn is the active path |

> **Never edit `extern/sd2snes` for Ciclone's sake.** HAL/header overrides win by `-I` ordering (same trick
> as the firmware's `tests/host/run.sh`). The exception is the `sd2snes` chip in bsnes (a new chip + the
> `// CICLONE` hooks),
> which lives **committed on the `ciclone-sd2snes-chip` branch** of the fork - `setup.sh` clones it already
> on that branch (it's not a local patch).

---

## Milestone status

| # | Milestone | State | Proof |
|---|---|---|---|
| **M0** | Foundations (harness + bsnes build) | done | `build_all` steps 1-3 |
| **M1** | Menu boots and draws | done | `build/frame.png` |
| **M2** | REAL firmware drives the menu (in-process) | done | `build/frame_fw.png` |
| **M2.5** | FxPakPro over serial (PTY), no real USB | done | `test_fxpak_info` + `test_fxpak_pty` |
| **M3** | Verilated FPGA, both sides (real RTL) | done | `test_vfpga_spi` + `test_vfpga_sim` |
| **M4** | REAL `.im3` boots in the emulator + FpgaModel via the seam | done | `lpc_emu` -> `menu_main_loop` |

**Updated to sd2snes+ 2.17 (3-bank menu) on 2026-09-28** (3-bank menu + `igmenu.bin`, ~50 firmware `.c`; S-RTC in the
behavioral model; headless button scripts).

**M4 in detail:** instead of Renode/QEMU (which lack the LPC176x family), `m4_unicorn/lpc_emu.c` emulates the
Cortex-M3 with the **Unicorn Engine** and hooks the LPC peripherals' MMIO. The real `.im3` boots fully
(clock/PLL, USB, mounts the `sdcard.img` FAT, opens `m3nu.bin`+`config.yml`, `SNES GO!`,
`test sram -> ok`) and reaches `menu_main_loop`. The firmware's SSP is wired to the **same FpgaModel as
M2/M3** through the SPI seam (`m4_unicorn/m4_glue.cpp`) - that's why `test sram` passes (memory round-trips
through the model).

---

## Gotchas / troubleshooting

- **`build_all` skips M4** -> `unicorn` is missing. `brew install unicorn`.
- **`build_gui.sh` fails** -> `sdl2` is missing (`brew install sdl2`) or `sdl2-config` is not on the PATH.
- **The window doesn't open / no focus** -> run from a Terminal with display access (a graphical macOS
  session); the binary is not an `.app` bundle, so it may open behind other windows - look in the dock/bar.
- **M4: `FALHA resolvendo simbolos`** -> the `.elf` doesn't match the `.im3`, or the build is *stripped*.
  Run `bash tools/fetch_m4fw.sh` after every `build.sh` (fetches the pair from the **same** build).
- **`firmware_lib/build.sh` fails with `undeclared`/`undefined`** after updating sd2snes -> a new `.c` landed
  in `src/` (add it to `FW_SRCS`) or a new define in `config-mk3` (mirror it in `hal_host/config.h`).
- **Changed `extern/bsnes-plus/bsnes/snes/cartridge/` and nothing happened** -> the `snes-cartridge.o` rule
  had a typo (`rwilddcard`); fixed on the chip branch. On an old tree, `rm obj/compatibility/snes-cartridge.o`.
- **Menu clock shows `88:88:88`** -> S-RTC reads (`$2800`) are not reaching the model: the bsnes chip must map
  MMIO from `$2800` (not `$2A00`).
- **`extern/` empty** -> run `bash tools/setup.sh`.
- **Verilator can't find `altpll`/`altsyncram`** -> they're provided by `fpga_model/stubs/` (the
  `verilate*.sh` scripts already include them).

---

## Licenses & credits

Ciclone builds on and links against GPL software, so **Ciclone's own code is under the GPL v2** - the
most restrictive common denominator, since bsnes-plus, the sd2snes firmware, and Unicorn are all GPL v2.
*This is a good-faith summary, not legal advice; verify before redistributing.*

| Component | License | Role in Ciclone | Credit |
|---|---|---|---|
| [bsnes-plus](https://github.com/devinacker/bsnes-plus) | GPL v2 | SNES core (`libsnes`) + the sd2snes chip | byuu/Near (bsnes) + bsnes-plus contributors |
| [sd2snes](https://github.com/mrehkopf/sd2snes) firmware | GPL v2 | the firmware under test (menu / MCU / FPGA sources) | Maximilian Rehkopf (ikari_01) + contributors; fork by ludufre |
| [Unicorn Engine](https://www.unicorn-engine.org/) | GPL v2 | M4 - Cortex-M3 CPU emulation (`lpc_emu`) | Nguyen Anh Quynh + contributors |
| [SDL2](https://libsdl.org/) | zlib | interactive window (`--gui`) | Sam Lantinga + SDL contributors |
| [Verilator](https://verilator.org/) | LGPLv3 / Artistic-2.0 | M3 - Verilog->C++ (generated model is permissive) | Wilson Snyder / Veripool |
| [Qt 5](https://www.qt.io/) | LGPLv3 | build-time dep of bsnes (not linked by Ciclone's binaries) | The Qt Company |
| [QUsb2snes](https://github.com/Skarsnik/QUsb2snes) | GPL v3 | reference for the FxPakPro protocol (not built/linked) | Sylvain "Skarsnik" Colinet |

The chip integration is committed on the `ciclone-sd2snes-chip` branch of the bsnes-plus fork, under
bsnes-plus's GPL v2. By binary: `host_runner*` link `libsnes` + the firmware (GPL v2) + SDL2 (zlib);
`lpc_emu` links Unicorn (GPL v2). SDL2 (zlib) is permissive and GPLv2-compatible.

