#!/usr/bin/env python3
"""Ciclone - run a Master System game on the SMS core, loaded THROUGH THE MENU, headless.

The whole real path: the menu, the firmware's .sms load (src/sms.c), the player of the tree
(snes/sms/sms_snes.asm) on bsnes, and the core's RTL (verilog/sd2snes_sms, Verilated) with the
main.v glue modelled around it (fpga_model/sms_model.cpp). Writes screenshots, the core's
counters and a per-SNES-frame log, and prints a summary.

  python3 tools/sms_run.py GAME.sms [--seconds 12] [--keys "300:B:10,600:RIGHT:240"]
                           [--shots 60,600,900 | --shot-every 60] [--out DIR] [--record]
  CICLONE_TREE=<firmware tree>      the RTL, the player and the firmware C of that tree (its own
                                    build dir, build/tree-<hash>/)
  --no-build                        reuse build/host_runner_fw as it is

--keys: F:BTN[+BTN][:HOLD] (frames after the game booted; BTN = B Y SEL START UP DOWN LEFT
RIGHT A X L R; HOLD default 4). The player forwards the SNES pad: B or A = button 1, Y or A =
button 2, the D-pad = the D-pad; SELECT/START do nothing (Pause is not wired).
Output dir (default build/sms-run/<game>): shot_<F>.png, stats.txt (the final counters,
key=value), sms.log (one line per SNES frame: sms= VDP frames, tr= translation passes started,
busy=/gate= frames without one, shown= buffers the player swapped in, empty= swaps with nothing
new, wrom= % of Z80 clocks waiting for PSRAM, trmax= longest pass in CLK2 cycles, nmi= lines the
player's NMI took, ctx/mcu/rd/wr= PSRAM slots per client), persec.txt (per second, distinct
pictures included), state.txt (the core at the end: Z80 PC, mapper banks, VDP registers, CRAM),
fw.log, and rec.video.mp4 with --record.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Another firmware tree gets its own build dir (runner, firmware objects, Verilated core,
# player): two runs against two trees never rebuild each other's runner.
if os.environ.get("CICLONE_TREE") and not os.environ.get("CICLONE_BUILD"):
    import hashlib
    _tag = hashlib.sha1(os.path.realpath(os.environ["CICLONE_TREE"]).encode()).hexdigest()[:10]
    os.environ["CICLONE_BUILD"] = str(ROOT / "build" / f"tree-{_tag}")
if os.environ.get("CICLONE_BUILD") and not os.environ.get("CICLONE_RUNNER"):
    os.environ["CICLONE_RUNNER"] = str(Path(os.environ["CICLONE_BUILD"]) / "host_runner_fw")
sys.path.insert(0, str(ROOT / "tests" / "menu"))
import ciclone as c  # noqa: E402


def parse_keys(spec: str) -> list[tuple[int, int, tuple[str, ...]]]:
    out = []
    for item in filter(None, (x.strip() for x in spec.split(","))):
        parts = item.split(":")
        f, btns = int(parts[0]), tuple(parts[1].split("+"))
        hold = int(parts[2]) if len(parts) > 2 else 4
        for b in btns:
            if b not in c.BUTTONS:
                raise SystemExit(f"botão desconhecido: {b}")
        out.append((f, f + hold, btns))
    return out


def per_second(out: Path, base: int) -> str:
    """One line per second of game: distinct pictures on screen (video.log, what a capture of
    the TV counts), buffers the player swapped in (shown), VDP frames that got no translation
    (gate = the previous one still unread, busy = a pass still running), the longest pass
    (CLK2 cycles) and the player's longest NMI (lines; the VBlank has 37)."""
    vid = [l.split() for l in (out / "video.log").read_text().splitlines()]
    vid = [int(ch) for f, ch, _ in vid if int(f) >= base]
    rows = [c.parse_kv(l) for l in (out / "sms.log").read_text().splitlines()]
    lines = ["  seg  distintos mostrados gate busy  trmax(clk2) nmi(linhas) wrom%\n"]
    for k in range(0, max(len(vid), len(rows)) // 60):
        v = vid[k * 60:(k + 1) * 60]
        r = rows[k * 60:(k + 1) * 60] or [{}]
        g = lambda key: sum(x.get(key, 0) for x in r)
        mx = lambda key: max(x.get(key, 0) for x in r)
        lines.append(f"  {k:3d}  {sum(v):9d} {g('shown'):9d} {g('gate'):4d} {g('busy'):4d} {mx('trmax'):12d} "
                     f"{mx('nmi'):11d} {sum(x.get('wrom', 0) for x in r) / len(r):5.1f}\n")
    return "".join(lines)


def boot(rom: bytes, workdir: Path, env: dict | None = None, name: str = "Game.sms") -> c.Menu:
    """Card with the game + the tree's player + a stand-in core file (the model does not read
    the bitstream), Ficha and the experimental-core question off: A on the file boots it."""
    sd = c.make_sd(workdir / "sd.img", config="---\nShowGameInfo: 0\nWarnExperimental: false\n",
                   extra={"/" + name: rom, "/sd2snes/fpga_sms.bi3": b"\0" * 1024,
                          "/sd2snes/sms_snes.bin": c.sms_player()})
    m = c.Menu(sd, workdir, env=env)
    m.step(60)
    m.settle()
    m.goto(name)
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot do jogo")
    if not m.sms():
        m.close()
        raise SystemExit("o runner não tem o core SMS (Verilator? CICLONE_SMS=0?): rode tools/build_runner.sh")
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("--seconds", type=float, default=12)
    ap.add_argument("--keys", default="")
    ap.add_argument("--shots", default="")
    ap.add_argument("--shot-every", type=int, default=0)
    ap.add_argument("--out")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()

    rom_path = Path(a.rom).expanduser()
    out = Path(a.out) if a.out else ROOT / "build" / "sms-run" / rom_path.stem.split(" (")[0].replace(" ", "_")
    out.mkdir(parents=True, exist_ok=True)
    if not a.no_build:
        import fcntl
        bdir = Path(os.environ.get("CICLONE_BUILD") or ROOT / "build")
        bdir.mkdir(parents=True, exist_ok=True)
        with open(bdir / ".build.lock", "w") as lk:      # two runs on one tree: one build at a time
            fcntl.flock(lk, fcntl.LOCK_EX)
            subprocess.run(["bash", str(ROOT / "tools" / "build_runner.sh")], check=True, stdout=sys.stderr)
            subprocess.run(["bash", str(ROOT / "tools" / "build_sms_player.sh")], check=True, stdout=sys.stderr)
    if not (c.MENU_DIR / "data.map").exists():
        raise SystemExit(f"sem o menu em {c.MENU_DIR}: rode tools/build_menu.sh")
    env = {"CICLONE_SMS_LOG": str(out / "sms.log"), "CICLONE_VIDEO_LOG": str(out / "video.log")}
    if a.record:
        env["CICLONE_RECORD"] = str(out / "rec")
    keys = parse_keys(a.keys)
    frames = int(a.seconds * 60.0988)
    shots = {int(x) for x in a.shots.split(",") if x.strip()}
    if a.shot_every:
        shots |= set(range(a.shot_every, frames + 1, a.shot_every))
    shots.add(frames)

    t0 = time.time()
    m = boot(rom_path.read_bytes(), out, env=env)
    base = m.frame
    print(f"[sms_run] jogo bootou no quadro {base} ({time.time() - t0:.1f} s)", flush=True)
    t1 = time.time()
    held: tuple[str, ...] = ()
    edges = sorted({f for k in keys for f in k[:2]} | shots | {frames})
    f = 0
    for e in edges:
        if e > frames:
            break
        if e > f:
            m.step(e - f)
            f = e
        want = tuple(sorted({b for (s, t, bs) in keys if s <= f < t for b in bs}))
        if want != held:
            m.hold(*want)
            held = want
        if f in shots:
            m.shot(out / f"shot_{f:05d}.png")
    st = m.sms()
    wall = time.time() - t1
    state = [f"pc={m.sms_peek('pc', 0, 2)[::-1].hex()}", f"bank={m.sms_peek('bank', 0, 3).hex()}",
             f"vreg={m.sms_peek('vreg', 0, 16).hex()}", f"cram={m.sms_peek('cram', 0, 32).hex()}"]
    (out / "state.txt").write_text("\n".join(state) + "\n")
    m.close()
    (out / "stats.txt").write_text(" ".join(f"{k}={v}" for k, v in st.items()) + "\n")
    secs = frames / 60.0988
    print(f"[sms_run] {secs:.1f} s de SNES em {wall:.1f} s ({secs / wall:.2f}x tempo real)")
    print(f"[sms_run] VDP {st.get('sms_frames')} quadros, mostrados {st.get('shown')} "
          f"({st.get('shown_fps')} por s), sem tradução: busy={st.get('tr_skip_busy')} gate={st.get('tr_skip_gate')}, "
          f"Z80 esperando PSRAM {100.0 * st.get('z80_wait_rom', 0) / max(1, st.get('z80_ce', 1)):.1f}% dos clocks, "
          f"NMI do player: média {st.get('nmi_lines_avg')} / máx {st.get('nmi_lines_max')} linhas "
          f"(estouros do VBlank: {st.get('nmi_overrun')})")
    table = per_second(out, base)
    (out / "persec.txt").write_text(table)
    print(table, end="")
    print(f"[sms_run] saída em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
