"""Savestate fix sources (tools/ssfix/*.s) vs what the firmware tree's savestate_fixes.yml carries,
and the assembler itself (tools/ss65.py). No console needed."""
import sys

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
import ss65  # noqa: E402

FIXES = c.SD2SNES / "savestate" / "savestate_fixes.yml"


def test_fix_sources_match_the_yml(t):
    """Editing a fix means editing its .s and regenerating the entry with ss65 -- never the hex."""
    yml = FIXES.read_text()
    sources = sorted((c.ROOT / "tools" / "ssfix").glob("*.s"))
    assert sources
    for src in sources:
        code, meta = ss65.assemble(src.read_text())
        have = ss65.yaml_blob(yml, meta["key"])
        assert have == code, f"{FIXES.name}: {meta['key']} != {src.name} -- python3 tools/ss65.py {src}"


def test_ss65_encodings(t):
    code, _ = ss65.assemble("""
        .a8
        .x16
        lda #$12            ; A 8-bit
        ldx #$1234          ; X 16-bit
        rep #$20            ; A -> 16
        lda #$1234
        sep #$30            ; A, X -> 8
        ldx #$12
        lda @$7E0100        ; forced long
        sta $1DFB,x
        lda $048D8A,x
    top: bne top
        brl top
        per top-1
        pea $804C
        jml $008134
        .db $6B
    """)
    assert code.hex().upper() == (
        "A912" "A23412" "C220" "A93412" "E230" "A212" "AF00017E" "9DFB1D" "BF8A8D04"
        "D0FE" "82FBFF" "62F7FF" "F44C80" "5C348100" "6B"), code.hex().upper()
