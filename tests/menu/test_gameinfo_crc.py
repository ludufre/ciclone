"""The ROM's CRC32 on the title row of the game info screen (snes/gicrc.a65 + gameinfo_crc_* in
src/gameinfo.c).

The firmware hashes the ROM in the background, one sector per pass of the menu loop, and publishes
the result in GI_CRC ($FF75C8: 8 hex digits + NUL, state, 'C','R'); the row shows "--------" until
then. The bytes hashed are the catalog's (the Manager's romSpan): minus a 512-byte copier header
when size % 1024 == 512, minus the iNES header of a .nes. The row shows the 8 digits alone, in the
value colour, right-aligned (no label). A revisited game is answered from a small
cache at once. A title wider than its field scrolls and never covers the CRC."""
import sys
import zlib

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
from sd_fixtures import lorom  # noqa: E402

GI_CRC = 0xFF75C8            # SRAM_GAMEINFO_CRC_ADDR
ST_PENDING, ST_READY = 1, 2
ROW = 17                     # the title row
TITLE_X, TITLE_W = 2, 51     # title cells 2..52, a blank at 53
HEX_X = 54                   # the 8 digits alone, 54..61 (right-aligned, no label)

PLAIN = lorom("CRC PLAIN")
HEADERED = bytes(512) + lorom("CRC HEADERED")
NES_PRG = bytes((i * 7 + 3) & 0xFF for i in range(0x8000))
NES = b"NES\x1a" + bytes([2, 1, 0, 0]) + bytes(8) + NES_PRG
LONG = ("A Very Long Game Title That Does Not Fit Next To The CRC Of The Row "
        "And Has To Scroll")                      # 87 chars, < GI_TITLEX_LEN, > TITLE_W


def _crc(b: bytes) -> str:
    return f"{zlib.crc32(b) & 0xFFFFFFFF:08X}"


def _card(t):
    sd = t.sd(config="---\nShowGameInfo: 1\n", extra={
        "/CRC/Alpha Plain.sfc": PLAIN,
        "/CRC/Beta Headered.sfc": HEADERED,
        "/CRC/Gamma Long.sfc": lorom("CRC LONG"),
        "/CRC/Delta.nes": NES,
        "/sd2snes/info/GA/Gamma Long.yml": f'---\ntitle: "{LONG}"\n'.encode(),
    })
    m = t.menu(sd)
    m.goto("CRC/")
    m.press("A")
    m.wait(lambda: m.has("Alpha Plain.sfc"), what="the folder")
    m.settle()
    return m


def _block(m):
    b = m.psram(GI_CRC, 12)
    return b[0:8].decode("latin-1"), b[9], b[10:12]


def _row(m) -> str:
    return m.screen()[ROW].ljust(64)


def _title(m) -> str:
    return _row(m)[TITLE_X:TITLE_X + TITLE_W].rstrip()


def _shows(m, title) -> bool:
    """The info screen is up with `title` at the start of its title row (the browser's rows
    above the body can still hold the file names, so m.has() would not do)."""
    return m.u16("screen_dma_disable") == 1 and _title(m).startswith(title)


def _open(m, name, title):
    m.goto(name)
    m.press("A")
    m.wait(lambda: _shows(m, title), what=f"the screen of {name}")


def _ready(m, want, what):
    m.wait(lambda: _block(m)[1] == ST_READY and _row(m)[HEX_X:HEX_X + 8] == want,
           frames=1800, what=what)
    row = _row(m)
    assert row[TITLE_X + TITLE_W:HEX_X] == " ", f"no blank before the digits\n{row}"
    assert row[HEX_X + 8:].strip() == "", f"something right of the digits\n{row}"
    assert "CRC" not in row[TITLE_X + TITLE_W:], f"a label next to the digits\n{row}"
    assert all(m.tile_at(x, ROW)[1] == 2 for x in range(HEX_X, HEX_X + 8)), "digits not in the value colour"
    assert _block(m) == (want, ST_READY, b"CR"), _block(m)


def test_crc_of_a_plain_rom(t):
    m = _card(t)
    _open(m, "Alpha Plain.sfc", "Alpha Plain")
    hexs, st, magic = _block(m)
    assert magic == b"CR" and st in (ST_PENDING, ST_READY), _block(m)
    if st == ST_PENDING:                       # the row says so until the hash is done
        assert _row(m)[HEX_X:HEX_X + 8] == "--------", _row(m)
    _ready(m, _crc(PLAIN), "the CRC of the plain ROM")
    m.settle()
    m.shot(t.dir / "crc_plain.png")
    m.close()


def test_copier_header_and_ines_header_are_left_out(t):
    m = _card(t)
    _open(m, "Beta Headered.sfc", "Beta Headered")
    _ready(m, _crc(HEADERED[512:]), "the CRC without the 512-byte header")
    assert _row(m)[HEX_X:HEX_X + 8] != _crc(HEADERED)
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="back in the browser")
    m.settle()
    _open(m, "Delta.nes", "Delta")
    _ready(m, _crc(NES_PRG), "the CRC of the .nes without its iNES header")
    m.close()


def test_long_title_scrolls_without_covering_the_crc(t):
    m = _card(t)
    _open(m, "Gamma Long.sfc", LONG[:20])
    want = _crc(lorom("CRC LONG"))
    _ready(m, want, "the CRC next to the long title")
    m.shot(t.dir / "crc_long_start.png")
    first = _title(m)
    assert first and first in LONG, first
    seen = {first}
    for _ in range(90):                        # ~1 s of hold, then a step every 10 frames
        m.step(10)
        row = _row(m)
        assert row[TITLE_X + TITLE_W] == " ", f"the title ran into the gap\n{row}"
        assert row[HEX_X:HEX_X + 8] == want, f"the CRC was covered\n{row}"
        part = _title(m)
        assert part and part in LONG, f"not a window of the title: {part!r}"
        seen.add(part)
        if part == LONG[-TITLE_W:] and not (t.dir / "crc_long_scrolled.png").exists():
            m.shot(t.dir / "crc_long_scrolled.png")   # the end of the title, the digits intact
    assert LONG[:TITLE_W] in seen, f"never showed the start: {sorted(seen)}"
    assert LONG[-TITLE_W:] in seen, f"never scrolled to the end: {sorted(seen)}"
    assert len(seen) > 10, "the title did not scroll"
    m.close()


def test_up_down_restarts_it_and_a_revisit_is_cached(t):
    m = _card(t)
    _open(m, "Alpha Plain.sfc", "Alpha Plain")
    _ready(m, _crc(PLAIN), "the first game's CRC")
    m.press("DOWN")                            # Beta Headered: a new hash, the old one dropped
    m.wait(lambda: _shows(m, "Beta Headered"), frames=1200, what="the next game's screen")
    _ready(m, _crc(HEADERED[512:]), "the next game's CRC")
    m.press("UP")                              # back: answered from the cache with the screen
    m.wait(lambda: _shows(m, "Alpha Plain"), frames=1200, what="the first game again")
    m.step(2)
    assert _block(m)[1] == ST_READY, "a revisit had to hash the ROM again"
    _ready(m, _crc(PLAIN), "the cached CRC on the row")
    m.close()
