"""Japanese (the first CJK language): ideographs are not in the 256-tile font, they come from a
glyph cache in VRAM (snes/cjk.a65). Each check here holds at every step of a walk through the
main menu and the Settings menu, whose descriptions need more glyphs than the cache has slots:

  - the tables agree: slot -> glyph -> the same slot;
  - VRAM holds, in every bound slot, exactly that glyph's tiles from the sheet (planes 0/1;
    planes 2/3 zero) -- a slot the NMI failed to upload, or uploaded late into active display
    (where VRAM writes are dropped), shows here;
  - no tilemap entry below the header points at a free slot (the collector freed something
    still on screen);
  - the collector runs and frees slots (the header's logo tiles $300+ fall in the slot range
    and once kept almost every slot alive)."""
import ciclone as c

LANG_JA = 8
G2S, S2G = 0x7F0000, 0x7F0400          # memmap.i65 CJK_G2S / CJK_S2G
VRAM_BASE, TILE0, NSLOTS = 0x3400, 0x340, 96
HEADER_ROWS = 9


def _slots(m):
    s2g = m.peek("wram", S2G - 0x7E0000, NSLOTS * 2)
    return {s: (s2g[2 * s] | s2g[2 * s + 1] << 8) - 1 for s in range(NSLOTS) if s2g[2 * s] | s2g[2 * s + 1]}


def _check(m, sheet, tag):
    vram = m.peek("vram", 0, 0x10000)
    g2s = m.peek("wram", G2S - 0x7E0000, 1024)
    slots = _slots(m)
    for s, g in slots.items():
        assert g2s[g] == s + 1, f"{tag}: slot {s} -> glyph {g} -> {g2s[g] - 1}"
        want = m.psram(sheet + g * 32, 32)
        base = (VRAM_BASE + s * 32) * 2
        got = vram[base:base + 16] + vram[base + 32:base + 48]
        assert got == want, f"{tag}: slot {s} (glyph {g}) VRAM {got.hex()} != sheet {want.hex()}"
        assert not any(vram[base + 16:base + 32] + vram[base + 48:base + 64]), f"{tag}: slot {s} planes 2/3"
    bg1 = m.wram(0x7EB000, 0x1000)              # BG1_TILE_BUF
    for i in range(64 * HEADER_ROWS, 0x1000, 2):
        tile = (bg1[i] | bg1[i + 1] << 8) & 0x3FF
        if TILE0 <= tile < TILE0 + 2 * NSLOTS and not tile & 1:
            assert (tile - TILE0) // 2 in slots, f"{tag}: row {i // 64} shows free slot {(tile - TILE0) // 2}"
    return len(slots)


def test_japanese_glyph_cache(t):
    m = t.menu(t.sd(config=f"---\nLanguage: {LANG_JA}\n"))
    assert m.u8("cur_lang") == LANG_JA
    sheet = m.sym["cjk_sheet"]
    m.press("X")
    m.settle()
    used = _check(m, sheet, "main menu")
    assert used > 20, f"main menu bound only {used} glyph slots: is it drawn in Japanese?"
    shrank = 0
    last = used
    for i in range(4):                            # down to Settings, one description per row
        m.press("DOWN"); m.step(4)
        last = _check(m, sheet, f"main {i}")
    m.press("A")
    m.settle()
    for rnd in range(2):                          # every Settings row, both ways: > 96 glyphs
        for key in ("DOWN", "UP"):
            for i in range(10):
                m.press(key); m.step(4)
                n = _check(m, sheet, f"settings {rnd} {key} {i}")
                shrank += n < last
                last = n
    m.press("B")
    m.settle()
    _check(m, sheet, "back to the main menu")
    assert shrank, "the walk never freed a slot: the collector did not run (or freed nothing)"
