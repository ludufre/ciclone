#!/usr/bin/env python3
"""Ciclone -- the menu suite on video, with sound (for showing it, not for checking it).

  python3 tools/record_suite.py [out.mp4] [-k pattern] [-j 4] [--speed 4]

Runs tests/menu/run.py with every console recorded (CICLONE_RECORD: the emulated frames and
the S-SMP + cartridge DAC sound, host_runner/runner.cpp) at the console's own speed
(CICLONE_SPEED=1, so the DAC plays right). The video is a grid with one quadrant per parallel
worker of run.py (2x2 for -j 4), each playing its runs back to back in the order it ran them,
the four sounds mixed, all sped up --speed times. Needs ffmpeg.
"""
import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "menu-tests"
W, H, AR = 512, 448, 48000
ENC_V = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "60"]
ENC_A = ["-c:a", "aac", "-b:a", "160k", "-ar", str(AR), "-ac", "2"]


def ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def duration(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", str(p)],
                                capture_output=True, text=True).stdout or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=str(ROOT / "build" / "ciclone-suite.mp4"))
    ap.add_argument("-k")
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--speed", type=float, default=4)
    ap.add_argument("--no-run", action="store_true", help="only rebuild the video from the last run")
    a = ap.parse_args()
    if not a.no_run:
        env = dict(os.environ, CICLONE_RECORD_DIR="1",
                   CICLONE_SPEED=os.environ.get("CICLONE_SPEED", "1"))
        cmd = [sys.executable, str(ROOT / "tests" / "menu" / "run.py"), "-j", str(a.j)]
        log = subprocess.run(cmd + (["-k", a.k] if a.k else []), env=env,
                             capture_output=True, text=True).stdout
        Path(a.out).with_suffix(".log").write_text(log)
        print(log.strip().splitlines()[-1] if log.strip() else "(sem saída)")

    runs = []                                    # (slot, t0, video, pcm)
    for meta in OUT.glob("*/run*/rec.json"):
        v = meta.with_name("rec.video.mp4")
        if v.exists() and v.stat().st_size and (not a.k or a.k in meta.parent.parent.name):
            m = json.loads(meta.read_text())
            runs.append((m["slot"], m["t0"], v, meta.with_name("rec.pcm")))
    slots = sorted({r[0] for r in runs})
    tmp = OUT / "_video"
    tmp.mkdir(parents=True, exist_ok=True)
    lanes = []
    for s in slots:
        segs = []
        for i, (_, _, v, pcm) in enumerate(sorted(r for r in runs if r[0] == s)):
            seg = tmp / f"s{s}_{i:03d}.mp4"
            ff("-i", str(v), "-f", "s16le", "-ar", "32040", "-ac", "2", "-i", str(pcm),
               "-vf", f"scale={W}:{H}:flags=neighbor", *ENC_V, *ENC_A, "-shortest", str(seg))
            segs.append(seg)
        lst = tmp / f"s{s}.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in segs))
        lane = tmp / f"lane{s}.mp4"
        ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(lane))
        lanes.append(lane)
        print(f"worker {s}: {len(segs)} runs, {duration(lane) / 60:.1f} min")
    n = len(lanes)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    longest = max(duration(l) for l in lanes)
    inputs, parts = [], []
    for i, lane in enumerate(lanes):
        inputs += ["-i", str(lane)]
        pad = longest - duration(lane) + 0.1
        parts.append(f"[{i}:v]tpad=stop_mode=clone:stop_duration={pad:.2f},setpts=PTS/{a.speed}[v{i}]")
        parts.append(f"[{i}:a]apad=whole_dur={longest:.2f}[a{i}]")
    layout = "|".join(f"{(i % cols) * W}_{(i // cols) * H}" for i in range(n))
    vin = "".join(f"[v{i}]" for i in range(n))
    ain = "".join(f"[a{i}]" for i in range(n))
    tempo, t = [], a.speed
    while t > 2:
        tempo.append("atempo=2")
        t /= 2
    tempo.append(f"atempo={t}")
    graph = ";".join(parts) + (f";{vin}xstack=inputs={n}:layout={layout}:fill=black[v]" if n > 1
                               else ";[v0]null[v]")
    graph += f";{ain}amix=inputs={n}:normalize=0,alimiter=limit=0.9,{','.join(tempo)}[a]"
    ff(*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", *ENC_V, *ENC_A,
       "-t", f"{longest / a.speed:.2f}", a.out)
    print(f"OK: {a.out} ({len(runs)} runs, {cols}x{rows}, {a.speed}x, {longest / a.speed / 60:.1f} min)")


if __name__ == "__main__":
    main()
