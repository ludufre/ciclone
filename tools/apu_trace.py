#!/usr/bin/env python3
"""Fold a CICLONE_TRACE_APU trace (host_runner) into what a game says to its sound CPU.

    CICLONE_TRACE_APU=build/apu.log  bash run/menu.sh        # or any --serve/--fw run
    python3 tools/apu_trace.py build/apu.log [--from F] [--to F] [--port 2142] [--burst 12]

Each trace line is one S-CPU write to $2140-$2143:
    <frame> <V>:<H> <port> <value> pc=<PB:PC> s=<S> ret=<12 bytes above S>

Output, in frame order:
  * UPLOAD  a frame with more than --burst writes: an IPL transfer (sound driver, samples, a song
            bank). Printed once per run of consecutive frames, with the PC that drove it and the
            call chain read off the stack -- the routine to call again from a savestate fix.
  * port changes outside uploads: the game's commands (song requests, sound effects, handshakes).

The call chain: after a JSR the stack holds the address of the JSR's last byte (low byte first),
so a 2-byte pair +1 is where the caller resumes and the JSR is 3 bytes before that. Pushed data
sits in between and alignment is unknown, so every byte pair pointing into the upper half of the
bank (where code lives) is listed: expect false candidates, check them against the ROM.
"""
from __future__ import annotations

import argparse
from collections import Counter


def parse(path):
    for line in open(path):
        p = line.split()
        if len(p) < 7:
            continue                                   # a line cut by the process exit
        yield {"frame": int(p[0]), "beam": p[1], "port": p[2], "value": int(p[3], 16),
               "pc": int(p[4][3:], 16), "s": int(p[5][2:], 16), "ret": bytes.fromhex(p[6][4:])}


def callers(ev) -> str:
    bank = ev["pc"] & 0xFF0000
    r = ev["ret"]
    out = []
    for i in range(len(r) - 1):
        ret = (r[i] | r[i + 1] << 8) + 1
        if ret >= 0x8003:
            out.append("jsr@$%06X" % (bank | (ret - 3)))
    return " ".join(out) or "-"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("trace")
    ap.add_argument("--from", dest="f0", type=int, default=0)
    ap.add_argument("--to", dest="f1", type=int, default=1 << 62)
    ap.add_argument("--port", action="append", help="only these ports' changes (e.g. 2142); repeatable")
    ap.add_argument("--burst", type=int, default=12, help="writes per frame above which it is an upload")
    ap.add_argument("--callers", action="store_true", help="the call chain on every port change too")
    a = ap.parse_args()

    events = [e for e in parse(a.trace) if a.f0 <= e["frame"] <= a.f1]
    per_frame = Counter(e["frame"] for e in events)
    last: dict[str, int] = {}
    upload_until = -2
    for e in events:
        f = e["frame"]
        if per_frame[f] > a.burst:
            if f > upload_until + 1:                   # a new run of upload frames
                end = f
                while per_frame.get(end + 1, 0) > a.burst:
                    end += 1
                print("%7d  UPLOAD frames %d-%d, pc=$%06X, callers: %s" % (f, f, end, e["pc"], callers(e)))
            upload_until = f
            last[e["port"]] = e["value"]
            continue
        if last.get(e["port"]) != e["value"] and (not a.port or e["port"] in a.port):
            prev = last.get(e["port"])
            print("%7d  $%s %s -> %02X  pc=$%06X%s" % (f, e["port"], "--" if prev is None else "%02X" % prev,
                                                      e["value"], e["pc"], "  " + callers(e) if a.callers else ""))
        last[e["port"]] = e["value"]


if __name__ == "__main__":
    main()
