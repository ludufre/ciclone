#!/usr/bin/env python3
"""ss65 -- a small 65816 assembler for savestate_fixes.yml code blobs.

    python3 tools/ss65.py tools/ssfix/smw_a0da.s                  # the YAML entry, ready to paste
    python3 tools/ss65.py tools/ssfix/smw_a0da.s --hex            # just the bytes
    python3 tools/ss65.py tools/ssfix/smw_a0da.s --check <yml>    # does the .yml carry exactly this?

A fix blob is `@<hex>` code the firmware copies to CS_FIXES ($FE1014) and the savestate handler
calls with JSL after every save and load (snes/savestate.a65 audio_fix), entered with A 8-bit and
X 16-bit, ended by the RTL the firmware appends. The YAML parser takes at most 64 bytes per `@`
item, so a longer blob is split over consecutive list items (they land back to back).

Source syntax (one instruction per line, `;` comments):
    ; key: A0DA                      the ROM header checksum the entry is for ($FFDE/$7FDE)
    ; name: super mario world (US)   text after the key on the entry line
    ;| ...                           a comment line copied into the entry (indented under the key)
    name = $FE1013                   a constant (its width = its hex digits: 2 dp, 4 abs, 6 long)
    label:  lda @name                labels end with ':'
            .a8 / .a16 / .x8 / .x16  declare the register sizes (rep/sep also track them)
            .db $6B, $00             raw bytes
Operands: #$12 / #name (immediate, sized by A or X), $12 (dp), $1234 (abs), $123456 or @$1234
(long), ,x / ,y indexing, a label for branches (8-bit), brl/per (16-bit, may be label+N / label-N).
Only the opcodes below exist -- add rows to OPS when a fix needs more.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# mnemonic -> {mode: opcode}. Modes: imp, imm (A-sized), immx (X-sized), imm8, dp, dpx, abs, absx,
# absy, long, longx, rel8, rel16, ind (jmp (abs)).
A_OPS = {  # the accumulator group: imm is A-sized
    "lda": {"imm": 0xA9, "dp": 0xA5, "dpx": 0xB5, "abs": 0xAD, "absx": 0xBD, "absy": 0xB9, "long": 0xAF, "longx": 0xBF},
    "sta": {"dp": 0x85, "dpx": 0x95, "abs": 0x8D, "absx": 0x9D, "absy": 0x99, "long": 0x8F, "longx": 0x9F},
    "cmp": {"imm": 0xC9, "dp": 0xC5, "abs": 0xCD, "absx": 0xDD, "absy": 0xD9, "long": 0xCF, "longx": 0xDF},
    "and": {"imm": 0x29, "dp": 0x25, "abs": 0x2D, "absx": 0x3D, "long": 0x2F, "longx": 0x3F},
    "ora": {"imm": 0x09, "dp": 0x05, "abs": 0x0D, "absx": 0x1D, "long": 0x0F, "longx": 0x1F},
    "eor": {"imm": 0x49, "dp": 0x45, "abs": 0x4D, "absx": 0x5D, "long": 0x4F, "longx": 0x5F},
    "adc": {"imm": 0x69, "dp": 0x65, "abs": 0x6D, "absx": 0x7D, "long": 0x6F, "longx": 0x7F},
    "sbc": {"imm": 0xE9, "dp": 0xE5, "abs": 0xED, "absx": 0xFD, "long": 0xEF, "longx": 0xFF},
    "bit": {"imm": 0x89, "dp": 0x24, "abs": 0x2C, "absx": 0x3C},
}
OPS = {
    **A_OPS,
    "ldx": {"immx": 0xA2, "dp": 0xA6, "abs": 0xAE, "absy": 0xBE},
    "ldy": {"immx": 0xA0, "dp": 0xA4, "abs": 0xAC, "absx": 0xBC},
    "cpx": {"immx": 0xE0, "dp": 0xE4, "abs": 0xEC},
    "cpy": {"immx": 0xC0, "dp": 0xC4, "abs": 0xCC},
    "stx": {"dp": 0x86, "abs": 0x8E},
    "sty": {"dp": 0x84, "abs": 0x8C},
    "stz": {"dp": 0x64, "dpx": 0x74, "abs": 0x9C, "absx": 0x9E},
    "inc": {"imp": 0x1A, "dp": 0xE6, "abs": 0xEE}, "dec": {"imp": 0x3A, "dp": 0xC6, "abs": 0xCE},
    "rep": {"imm8": 0xC2}, "sep": {"imm8": 0xE2},
    "jmp": {"abs": 0x4C, "ind": 0x6C}, "jml": {"long": 0x5C}, "jsr": {"abs": 0x20}, "jsl": {"long": 0x22},
    "pea": {"abs": 0xF4}, "pei": {"dp": 0xD4}, "per": {"rel16": 0x62}, "brl": {"rel16": 0x82},
    **{b: {"rel8": o} for b, o in (("bpl", 0x10), ("bmi", 0x30), ("bvc", 0x50), ("bvs", 0x70), ("bra", 0x80),
                                    ("bcc", 0x90), ("bcs", 0xB0), ("bne", 0xD0), ("beq", 0xF0))},
    **{m: {"imp": o} for m, o in (
        ("rts", 0x60), ("rtl", 0x6B), ("rti", 0x40), ("php", 0x08), ("plp", 0x28), ("pha", 0x48), ("pla", 0x68),
        ("phx", 0xDA), ("plx", 0xFA), ("phy", 0x5A), ("ply", 0x7A), ("phb", 0x8B), ("plb", 0xAB), ("phd", 0x0B),
        ("pld", 0x2B), ("phk", 0x4B), ("tax", 0xAA), ("tay", 0xA8), ("txa", 0x8A), ("tya", 0x98), ("txy", 0x9B),
        ("tyx", 0xBB), ("tcd", 0x5B), ("tdc", 0x7B), ("tcs", 0x1B), ("tsc", 0x3B), ("txs", 0x9A), ("tsx", 0xBA),
        ("xba", 0xEB), ("inx", 0xE8), ("iny", 0xC8), ("dex", 0xCA), ("dey", 0x88), ("clc", 0x18), ("sec", 0x38),
        ("cli", 0x58), ("sei", 0x78), ("nop", 0xEA), ("wai", 0xCB), ("xce", 0xFB))},
}
SIZE = {"imp": 0, "imm8": 1, "dp": 1, "dpx": 1, "abs": 2, "absx": 2, "absy": 2, "ind": 2, "long": 3,
        "longx": 3, "rel8": 1, "rel16": 2}


class AsmError(Exception):
    pass


def number(tok: str, consts: dict) -> tuple[int, int]:
    """(value, hex digits) of $hex / decimal / a constant."""
    if tok.startswith("$"):
        return int(tok[1:], 16), len(tok) - 1
    if tok in consts:
        return consts[tok]
    if tok.isdigit():
        return int(tok), 2 if int(tok) < 256 else 4
    raise AsmError(f"unknown value {tok!r}")


def assemble(src: str) -> tuple[bytes, dict]:
    meta = {"key": None, "name": "", "notes": []}
    consts: dict[str, tuple[int, int]] = {}
    lines = []
    for n, raw in enumerate(src.splitlines(), 1):
        if raw.lstrip().startswith(";|"):
            meta["notes"].append(raw.lstrip()[2:].rstrip())
            continue
        m = re.match(r"\s*;\s*(key|name):\s*(.*)", raw)
        if m:
            meta[m.group(1)] = m.group(2).strip()
            continue
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"(\w+)\s*=\s*(\$[0-9A-Fa-f]+)$", line)
        if m:
            consts[m.group(1)] = number(m.group(2), {})
            continue
        m = re.match(r"(\w+):\s*(.*)", line)
        label, rest = (m.group(1), m.group(2)) if m else (None, line)
        lines.append((n, label, rest))

    def encode(rest, pc, labels, sizes, final):
        """(bytes, new sizes) for one statement at pc; labels may be incomplete when not final."""
        if not rest:
            return b"", sizes
        mnem, _, arg = rest.partition(" ")
        mnem, arg = mnem.lower(), arg.strip().replace(" ", "")
        if mnem in (".a8", ".a16", ".x8", ".x16"):
            reg, bits = mnem[1], int(mnem[2:])
            return b"", {**sizes, reg: bits}
        if mnem == ".db":
            return bytes(number(v, consts)[0] & 0xFF for v in arg.split(",")), sizes
        if mnem not in OPS:
            raise AsmError(f"unknown mnemonic {mnem!r}")
        modes = OPS[mnem]
        if not arg:
            if "imp" not in modes:
                raise AsmError(f"{mnem} needs an operand")
            return bytes([modes["imp"]]), sizes
        if "rel8" in modes or "rel16" in modes:
            mode = "rel8" if "rel8" in modes else "rel16"
            m = re.match(r"(\w+)([+-]\d+)?$", arg)
            if not m:
                raise AsmError(f"bad branch target {arg!r}")
            target = labels.get(m.group(1))
            if target is None:
                if final:
                    raise AsmError(f"unknown label {m.group(1)!r}")
                target = pc
            target += int(m.group(2) or 0)
            end = pc + 1 + SIZE[mode]
            d = target - end
            if mode == "rel8":
                if final and not -128 <= d < 128:
                    raise AsmError(f"branch to {arg} out of range ({d})")
                return bytes([modes[mode], d & 0xFF]), sizes
            return bytes([modes[mode], d & 0xFF, (d >> 8) & 0xFF]), sizes
        if arg.startswith("#"):
            v, _ = number(arg[1:], consts)
            if mnem in ("rep", "sep"):
                a16 = sizes["a"] if not v & 0x20 else (16 if mnem == "rep" else 8)
                x16 = sizes["x"] if not v & 0x10 else (16 if mnem == "rep" else 8)
                return bytes([modes["imm8"], v & 0xFF]), {"a": a16, "x": x16}
            mode = "immx" if "immx" in modes else "imm"
            if mode not in modes:
                raise AsmError(f"{mnem} has no immediate mode")
            width = sizes["x" if mode == "immx" else "a"] // 8
            return bytes([modes[mode]]) + v.to_bytes(width, "little"), sizes
        if arg.startswith("(") and arg.endswith(")"):
            v, _ = number(arg[1:-1], consts)
            return bytes([modes["ind"]]) + v.to_bytes(2, "little"), sizes
        forced_long = arg.startswith("@")
        base, _, index = arg.lstrip("@").partition(",")
        v, digits = number(base, consts)
        kind = "long" if forced_long or digits > 4 else "abs" if digits > 2 else "dp"
        mode = kind + (index.lower() if index else "")
        if mode not in modes:
            raise AsmError(f"{mnem} has no {mode} mode")
        return bytes([modes[mode]]) + v.to_bytes(SIZE[mode], "little"), sizes

    def run(labels, final):
        out, sizes, new_labels = bytearray(), {"a": 8, "x": 16}, {}
        for n, label, rest in lines:
            if label:
                new_labels[label] = len(out)
            try:
                b, sizes = encode(rest, len(out), labels, sizes, final)
            except AsmError as e:
                raise AsmError(f"line {n}: {e}") from None
            out += b
        return bytes(out), new_labels

    _, labels = run({}, False)          # pass 1: label addresses (branch sizes are fixed per opcode)
    code, _ = run(labels, True)
    return code, meta


def yaml_entry(code: bytes, meta: dict) -> str:
    if not meta["key"]:
        raise AsmError("no '; key: XXXX' line in the source")
    head = f"{meta['key']}:" + (f" # {meta['name']}" if meta["name"] else "")
    notes = [f"      #{t}" if t else "      #" for t in meta["notes"]]
    items = [f"  - @{code[i:i + 64].hex().upper()}" for i in range(0, len(code), 64)]
    return "\n".join([head, *notes, *items]) + "\n"


def yaml_blob(yml: str, key: str) -> bytes | None:
    """The code bytes of `key`'s @ list items in a savestate_fixes.yml, or None."""
    lines = yml.splitlines()
    for i, l in enumerate(lines):
        if l.split("#")[0].strip() == f"{key}:":
            out = b""
            for l2 in lines[i + 1:]:
                s = l2.strip()
                if s.startswith("#") or not s:
                    continue
                if not s.startswith("- @"):
                    break
                out += bytes.fromhex(s[3:].split("#")[0].strip())
            return out
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source")
    ap.add_argument("--hex", action="store_true", help="print the bytes only")
    ap.add_argument("--check", metavar="YML", help="exit 1 unless YML carries exactly these bytes for the key")
    a = ap.parse_args()
    try:
        code, meta = assemble(Path(a.source).read_text())
    except AsmError as e:
        sys.exit(f"{a.source}: {e}")
    if a.check:
        have = yaml_blob(Path(a.check).read_text(), meta["key"])
        if have != code:
            sys.exit(f"{a.check}: {meta['key']} does not match {a.source} ({len(code)} bytes)")
        print(f"ok: {meta['key']} in {a.check} = {a.source} ({len(code)} bytes)")
    elif a.hex:
        print(code.hex().upper())
    else:
        print(yaml_entry(code, meta), end="")


if __name__ == "__main__":
    main()
