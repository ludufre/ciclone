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
G2S2, S2G2, NSLOTS2 = 0x7F1100, 0x7F1400, 128
HEADER_ROWS = 9


def _w(m, addr, n):
    return m.peek("wram", addr - W, n)


def _slots(m):
    s2g = _w(m, S2G, NSLOTS * 2)
    return {s: (s2g[2 * s] | s2g[2 * s + 1] << 8) - 1 for s in range(NSLOTS) if s2g[2 * s] | s2g[2 * s + 1]}


def _glyph64(m, g, sheet, lang_sheet):
    if g < 128:
        return m.psram(sheet + g * 64, 64)                       # resident sheet
    if g < 640:
        return _w(m, 0x7F0000 + lang_sheet + (g - 128) * 64, 64)  # the language's, in WRAM
    return m.psram(GI_CJK_SHEET + (g - 640) * 64, 64)            # a game's text, by the firmware


def _check(m, tag, body_from=HEADER_ROWS):
    for _ in range(120):                          # the NMI sends what is queued, a few a frame
        if not _w(m, 0x7F0940, 1)[0]:
            break
        m.step(1)
    assert not _w(m, 0x7F0940, 1)[0], f"{tag}: glyphs still queued for VRAM after 120 frames"
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
        want = _glyph64(m, g, sheet, lang_sheet)
        got = vram[tile * 32:tile * 32 + 64]
        assert got == want, f"{tag}: slot {s} (glyph {g}, tile {tile:#x}) VRAM != sheet"
    bg1 = m.wram(0x7EB000, 0x1000)
    for i in range(64 * body_from, 0x1000, 2):
        tile = (bg1[i] | bg1[i + 1] << 8) & 0x3FF
        if tile in slot_tiles and tile not in bound:
            raise AssertionError(f"{tag}: row {i // 64} shows tile {tile:#x}, a free slot")
    # the BG2 pool: a glyph starting on an even column, in a BG2 cell of the maps' lower screens
    g2s2 = _w(m, G2S2, 768)
    s2g2 = _w(m, S2G2, 2 * NSLOTS2)
    bound2 = set()
    for s in range(NSLOTS2):
        v = s2g2[2 * s] | s2g2[2 * s + 1] << 8
        if not v:
            continue
        g = v - 1
        assert g2s2[g] == s + 1, f"{tag}: BG2 slot {s} -> glyph {g} -> {g2s2[g] - 1}"
        tile = 640 + 2 * s if s < 64 else 768 + 2 * s
        bound2.add(tile)
        want = _glyph64(m, g, sheet, lang_sheet)
        got = vram[(0x4000 + 8 * tile) * 2:(0x4000 + 8 * tile) * 2 + 32]
        assert got == want[0:16] + want[32:48], (f"{tag}: BG2 slot {s} (glyph {g}) VRAM != sheet\n"
            f"right half found at word {[hex(i//2) for i in range(0,len(vram)-16,2) if vram[i:i+16]==want[32:48]][:5]} tile {tile} slot word {0x4000+8*tile:#x}\n"
            f"got  {got.hex()}\nwant {(want[0:16] + want[32:48]).hex()}\ndirty {_w(m, 0x7F1500, 8).hex()} nd {_w(m, 0x7F0940, 1).hex()}")
    bg2 = m.wram(0x7EA000, 0x1000)
    for i in range(64 * body_from, 64 * 32, 2):
        tile = (bg2[i] | bg2[i + 1] << 8) & 0x3FF
        if (640 <= tile < 768 or tile >= 896) and not tile & 1 and tile not in bound2:
            raise AssertionError(f"{tag}: BG2 row {i // 64} shows tile {tile:#x}, a free BG2 cell")
    tofu = _w(m, TOFU, 1)[0]
    assert tofu == 0, f"{tag}: {tofu} glyph(s) printed as '?' (no slot free)"
    return len(slots) + len(bound2)


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
    for i in range(1, 8):                         # its submenus (rows 1..7; row 8 runs the tour)
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


def _lang_edit(m, btn, n):
    """Main menu's Language row: open the value, n x btn, commit."""
    m.press("A"); m.settle()
    for _ in range(n):
        m.press(btn, hold=6, after=6); m.step(20)
    m.press("A"); m.settle()


def test_language_change_out_of_and_into_cjk(t):
    """Japanese -> English -> Japanese from the main menu. The menu must stay responsive
    (a waitblank-style wait used to starve when the NMI ran past the end of VBlank)."""
    m = t.menu(t.sd(config=f"---\nLanguage: {LANG_JA}\n"))
    m.press("X"); m.settle()
    for _ in range(5):
        m.press("DOWN"); m.step(3)
    _lang_edit(m, "DOWN", 8)                       # ja -> nl ... -> en
    assert m.u8("cur_lang") == 0, f"commit left cur_lang {m.u8('cur_lang')}"
    assert m.has(c.tr("text_mainmenu")), m.text()
    for _ in range(8):                             # the bar back on the Language row
        if "Language" in m.bar_row():
            break
        m.press("DOWN"); m.step(4)
    _lang_edit(m, "UP", 8)                         # en -> ... -> ja (loads its file)
    assert m.u8("cur_lang") == LANG_JA and _w(m, LANG_CUR, 1)[0] == LANG_JA, \
        f"cur_lang {m.u8('cur_lang')} file {_w(m, LANG_CUR, 1)[0]}"
    assert _check(m, "back in Japanese") > 10
    m.press("UP"); m.step(10)                      # still answering the pad
    m.press("B"); m.settle()
    assert m.u16("window_stack_head") == 0xFFFF, f"the menu did not close ({m.u16('window_stack_head'):#x})"


def test_list_cover_with_a_full_cache(t):
    """Favorites with a cover after a walk that filled region A with glyphs no longer shown:
    the cover takes region B, so the list title's glyphs there must move to A -- freeing A
    slots nothing shows first. Without that they were dropped and the title showed the cover's
    tiles (seen on a Mk.III)."""
    sd = t.sd(config=f"---\nLanguage: {LANG_JA}\n",
              extra={"/sd2snes/favorites.cfg": b"/Test Game.sfc\n",
                     "/Test Game.cov": _cov(6, 8)})
    m = t.menu(sd)
    _walk_settings(m)
    a_bound = sum(1 for s in _slots(m) if s < 96)
    m.settle()
    m.press("SEL")
    m.wait(lambda: m.u16("window_stack_head") != 0xFFFF, frames=300, what="the favorites list")
    m.wait(lambda: m.u8("cover_loaded") == 1, frames=600, what="the favorite's cover")
    m.settle()
    _check(m, f"favorites with a cover (A had {a_bound} bound)")
    m.shot(t.dir / "favorites_cover.png")


def _cell_left_of_window(m):
    """Rows of the drawn window whose column window_x-1 starts a glyph cell (it would spill
    onto the window's left border)."""
    x, y, h = m.u8("window_x"), m.u8("window_y"), m.u8("window_h")
    c = x - 1
    buf = m.wram(0x7EB000 if c & 1 else 0x7EA000, 0x1000)
    bad = []
    for r in range(y, y + h):
        tile = (buf[r * 64 + (c & ~1)] | buf[r * 64 + (c & ~1) + 1] << 8) & 0x3FF
        if (c & 1 and 0x200 <= tile < 0x400 and not tile & 1) or \
           (not c & 1 and (640 <= tile < 768 or tile >= 896) and not tile & 1):
            bad.append((r, hex(tile)))
    return bad


def test_window_border_hides_the_glyph_it_cuts(t):
    """System Information opens over the main menu at an even column: the first glyph of the
    main menu's title sat in the column just left of it, half under the new border. It is
    blanked while the window is up and comes back when it closes."""
    m = t.menu(t.sd(config=f"---\nLanguage: {LANG_JA}\n"))
    m.press("X"); m.settle()
    m.press("DOWN"); m.step(4); m.press("DOWN"); m.settle()
    before = m.wram(0x7EA000, 0x1000) + m.wram(0x7EB000, 0x1000)
    m.press("A"); m.settle(); m.step(30)
    assert m.u8("window_x") == 10, f"System Information moved: window_x {m.u8('window_x')}"
    assert not _cell_left_of_window(m), _cell_left_of_window(m)
    _check(m, "system information")
    m.press("B"); m.settle()
    after = m.wram(0x7EA000, 0x1000) + m.wram(0x7EB000, 0x1000)
    title = [i for i in range(0, 0x2000, 64) if before[i:i + 64] != after[i:i + 64]]
    assert not title, f"rows not restored after closing: {[((i % 0x1000) // 64, i // 0x1000) for i in title][:8]}"
    _check(m, "back to the main menu")
