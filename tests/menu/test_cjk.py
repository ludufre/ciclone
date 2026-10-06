"""CJK menu languages (ja = 8, zh = 9): ideographs are not in the 256-tile font, they come
from a glyph cache in VRAM (snes/cjk.a65), and each language's strings + glyphs are a file on
the card (/sd2snes/lang/<code>.bin) the menu copies into WRAM $7F. Checked at every step of
a walk through the main menu, Settings and its submenus:

  - the tables agree: slot -> glyph -> the same slot;
  - VRAM holds, at every bound slot's tile, exactly that glyph's 64 bytes from its sheet
    (resident sheet in the menu image, or the language's in WRAM) -- a slot the NMI failed to
    upload, or uploaded late into active display (where VRAM writes are dropped), shows here;
  - no tilemap entry below the header points at a free slot;
  - no glyph ever printed as '?' for lack of a slot (CJK_TOFU);
  - the collector runs and frees slots.
Plus: the game-info screen with a cover (its band takes the slot area: the glyphs move into
the band's empty tiles), and a card without the language file (English)."""
import ciclone as c

LANG_JA, LANG_ZH = 8, 9
W = 0x7E0000
G2S, S2G, SLOT_TILE, TOFU, LANG_CUR, MODE = 0x7F0000, 0x7F0300, 0x7F0680, 0x7F0941, 0x7F0942, 0x7F0945
LANG_SHEET = 0x7F2008
GI_CJK_SHEET = 0xCBC000
NSLOTS = 224
HEADER_ROWS = 9


def _w(m, addr, n):
    return m.peek("wram", addr - W, n)


def _slots(m):
    s2g = _w(m, S2G, NSLOTS * 2)
    return {s: (s2g[2 * s] | s2g[2 * s + 1] << 8) - 1 for s in range(NSLOTS) if s2g[2 * s] | s2g[2 * s + 1]}


def _check(m, tag, body_from=HEADER_ROWS):
    vram = m.peek("vram", 0, 0x10000)
    g2s = _w(m, G2S, 768)
    st = _w(m, SLOT_TILE, NSLOTS * 2)
    slot_tiles = {st[2 * s] | st[2 * s + 1] << 8 for s in range(NSLOTS)}
    sheet = m.sym["cjk_sheet"]
    lang_sheet = int.from_bytes(_w(m, LANG_SHEET, 2), "little")
    slots = _slots(m)
    bound = set()
    for s, g in slots.items():
        assert g2s[g] == s + 1, f"{tag}: slot {s} -> glyph {g} -> {g2s[g] - 1}"
        tile = st[2 * s] | st[2 * s + 1] << 8
        bound.add(tile)
        if g < 128:
            want = m.psram(sheet + g * 64, 64)                      # resident sheet
        elif g < 640:
            want = _w(m, 0x7F0000 + lang_sheet + (g - 128) * 64, 64)  # the language's, in WRAM
        else:
            want = m.psram(GI_CJK_SHEET + (g - 640) * 64, 64)       # a game's text, by the firmware
        got = vram[tile * 32:tile * 32 + 64]
        assert got == want, f"{tag}: slot {s} (glyph {g}, tile {tile:#x}) VRAM != sheet"
    bg1 = m.wram(0x7EB000, 0x1000)
    for i in range(64 * body_from, 0x1000, 2):
        tile = (bg1[i] | bg1[i + 1] << 8) & 0x3FF
        if tile in slot_tiles and tile not in bound:
            raise AssertionError(f"{tag}: row {i // 64} shows tile {tile:#x}, a free slot")
    tofu = _w(m, TOFU, 1)[0]
    assert tofu == 0, f"{tag}: {tofu} glyph(s) printed as '?' (no slot free)"
    return len(slots)


def _walk_settings(m):
    m.press("X")
    m.settle()
    used = _check(m, "main menu")
    assert used > 20, f"main menu bound only {used} slots: is it drawn in CJK?"
    for i in range(4):
        m.press("DOWN"); m.step(4)
        _check(m, f"main {i}")
    m.press("A")                                  # Settings
    m.settle()
    last, shrank = _check(m, "settings"), 0
    for i in range(1, 9):                         # its submenus (rows 1..8)
        m.press("DOWN"); m.step(4)
        m.press("A"); m.settle()
        for j in range(14):
            m.press("DOWN"); m.step(3)
            n = _check(m, f"submenu {i} row {j}")
            shrank += n < last
            last = n
        m.press("B"); m.settle()
        _check(m, f"back from submenu {i}")
    m.press("B"); m.settle()
    m.press("B"); m.settle()
    _check(m, "back to the browser")
    return shrank


def test_japanese_glyph_cache(t):
    m = t.menu(t.sd(config=f"---\nLanguage: {LANG_JA}\n"))
    assert m.u8("cur_lang") == LANG_JA and _w(m, LANG_CUR, 1)[0] == LANG_JA
    assert _walk_settings(m), "the walk never freed a slot: the collector did not run"


def test_chinese_glyph_cache(t):
    m = t.menu(t.sd(config=f"---\nLanguage: {LANG_ZH}\n"))
    assert m.u8("cur_lang") == LANG_ZH and _w(m, LANG_CUR, 1)[0] == LANG_ZH
    _walk_settings(m)


def test_missing_language_file_falls_back_to_english(t):
    m = t.menu(t.sd(config=f"---\nLanguage: {LANG_JA}\n", lang=False))
    assert m.u8("cur_lang") == 0, "no /sd2snes/lang/ja.bin: the menu must run in English"
    m.press("X")
    m.settle()
    assert m.has(c.tr("text_mainmenu")), m.text()


def _cov(w, h):
    hdr = bytes([ord("C"), ord("V"), 4, 0, w, h, 1, 0, 4, 0, 0, 0])
    pal = b"\x00\x00" + b"".join(((i * 0x0842) & 0x7FFF).to_bytes(2, "little") for i in range(1, 16))
    return hdr + pal + bytes(w * h) + bytes([0xAA, 0x55] * 8 + [0xFF, 0x0F] * 8) * (2 * h * 16 * w // 2)


def test_japanese_game_info_with_cover(t):
    from test_gameinfo_assets import YML
    sd = t.sd(config=f"---\nShowGameInfo: 1\nLanguage: {LANG_JA}\n",
              extra={"/sd2snes/info/TE/Test Game.yml": YML, "/Test Game.cov": _cov(6, 8)})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.settle()
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game-info screen")
    m.settle()
    assert _w(m, MODE, 1)[0] == 1, "the game-info screen did not switch the cache to its band"
    assert _check(m, "game info", body_from=16) > 5, "the game-info body bound no glyph"
    m.shot(t.dir / "game_info.png")
    m.press("B")
    m.settle()
    assert _w(m, MODE, 1)[0] == 0, "back from the game-info screen: the cache is still in its mode"
    _check(m, "back from game info")


YML_JA = ("---\n"
          'title: "Probe Title"\n'
          'description: "English probe text"\n'
          'title_ja: "スーパーマリオワールド"\n'
          'description_ja: "恐竜ランドを舞台に、マリオとヨッシーが大冒険。7つの城を攻略して、さらわれたピーチ姫を救い出そう。'
          '隠しゴールや秘密のコースもたくさん。SFC本体と同時発売された、シリーズを代表する一本です。"\n').encode()


def test_japanese_game_text_from_the_yml(t):
    """title_ja / description_ja: the firmware indexes the game's ideographs, draws them from
    /sd2snes/lang/ja.fnt into GI_CJK_SHEET, and the menu uploads them as glyphs 640+."""
    sd = t.sd(config=f"---\nShowGameInfo: 1\nLanguage: {LANG_JA}\n",
              extra={"/sd2snes/info/TE/Test Game.yml": YML_JA, "/Test Game.cov": _cov(6, 8)})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.settle()
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game-info screen")
    m.settle()
    game = [g for g in _slots(m).values() if g >= 640]
    assert len(game) > 20, f"only {len(game)} game-text glyphs bound: title/description not in Japanese?"
    _check(m, "game info (Japanese text)", body_from=16)
    m.shot(t.dir / "game_info_ja.png")
    m.press("Y")                                   # the full description
    m.settle()
    _check(m, "full description", body_from=16)
    m.shot(t.dir / "game_info_ja_full.png")
