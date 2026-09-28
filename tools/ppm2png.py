#!/usr/bin/env python3
"""Converte PPM (P6) -> PNG usando só a stdlib (zlib). uso: ppm2png.py in.ppm out.png"""
import sys, zlib, struct

def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        data = f.read()
    assert data[:2] == b"P6", "esperado PPM P6"
    idx, toks = 2, []
    while len(toks) < 3:
        while idx < len(data) and data[idx:idx+1].isspace():
            idx += 1
        if data[idx:idx+1] == b"#":
            while idx < len(data) and data[idx:idx+1] != b"\n":
                idx += 1
            continue
        start = idx
        while idx < len(data) and not data[idx:idx+1].isspace():
            idx += 1
        toks.append(int(data[start:idx]))
    idx += 1  # único whitespace após maxval
    w, h, _mx = toks
    raw = data[idx:idx + w*h*3]

    def chunk(typ, payload):
        return (struct.pack(">I", len(payload)) + typ + payload
                + struct.pack(">I", zlib.crc32(typ + payload) & 0xffffffff))

    rows = bytearray()
    stride = w * 3
    for y in range(h):
        rows.append(0)              # filtro 0 (None) por scanline
        rows += raw[y*stride:(y+1)*stride]

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
           + chunk(b"IEND", b""))
    with open(dst, "wb") as f:
        f.write(png)
    print(f"{w}x{h} -> {dst}")

main()
