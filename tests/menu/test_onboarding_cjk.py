"""The tour in Japanese (8) and Chinese (9): its 256-character font has no ideographs, so a
CJK glyph is drawn as ONE BG2 cell from a cache in the BG2/BG1 tilemaps' unused lower
screens (snes/onboarding/onb_cjk.a65: tiles 640..767 and 896..1023, 128 cells). Walked card
by card, and through the language card's live switch, checking at every step:

  - the tables agree: slot -> glyph -> the same slot;
  - VRAM holds, at every bound slot, exactly that glyph drawn as gen_onb_lang.py draws it
    (each pixel doubled, the font's contour) -- a cell the NMI failed to upload, or uploaded
    into active display (dropped), shows here;
  - no BG2 tilemap entry of the screen points at a free cell;
  - nothing printed as '?' for lack of a cell or a sheet (OCJ_TOFU);
  - nothing left to upload once the screen settles."""
import os
from pathlib import Path
import sys

import ciclone as c

sys.path.insert(0, str(c.SD2SNES / "snes" / "utils"))
import gen_onb_lang as onb  # noqa: E402
sys.path.pop(0)

LANG_JA, LANG_ZH = 8, 9
W = 0x7E0000
G2S, S2G, OCJ_LANG, TOFU, LO, HI = 0x7F4000, 0x7F4300, 0x7F4501, 0x7F4502, 0x7F4504, 0x7F4506
NSLOTS = 128
S2K = 0x7F4600
BG2_TILE_BUF = 0x7EA000
SHOTS = os.environ.get("ONB_SHOTS")

COMMON, LANG_MAPS, FONTS, COMMON_FONT = onb.cjk_maps()
CHARS = {"common": {i: ch for ch, i in COMMON.items()}}
for _l, _m in LANG_MAPS.items():
    CHARS[_l] = {i: ch for ch, i in _m.items()}


def _w(m, addr, n):
    return m.peek("wram", addr - W, n)


def _want(g, lang):
    if g < 128:
        ch = CHARS["common"][g]
        return onb._glyph_2bpp(FONTS[COMMON_FONT[ch]][ch])
    ch = CHARS[lang][g]
    return onb._glyph_2bpp(FONTS[lang][ch])


def _slot_tile(s):
    return 640 + 2 * s if s < 64 else 768 + 2 * s


def _check(m, tag, lang=None):
    """lang: the CJK language the cached glyphs 128+ must be from (None: the cache's own,
    OCJ_LANG -- a Latin language leaves the last CJK one's glyphs bound, unseen)."""
    if lang is None:
        lang = ["ja", "zh"][_w(m, OCJ_LANG, 1)[0] - LANG_JA] if _w(m, OCJ_LANG, 1)[0] >= LANG_JA else None
    vram = m.peek("vram", 0, 0x10000)
    g2s = _w(m, G2S, 768)
    s2g = _w(m, S2G, 2 * NSLOTS)
    s2k = _w(m, S2K, 2 * NSLOTS)
    bound = {}
    for s in range(NSLOTS):
        v = s2g[2 * s] | s2g[2 * s + 1] << 8
        if not v:
            continue
        t = _slot_tile(s)
        got = vram[(0x4000 + 8 * t) * 2:(0x4000 + 8 * t) * 2 + 32]
        if v & 0x8000:                             # a pair cell: right half of a, left of b
            a, b = v & 0x7FFF, s2k[2 * s] | s2k[2 * s + 1] << 8
            want = (_want(a - 1, lang)[16:] if a else bytes(16)) + (_want(b - 1, lang)[:16] if b else bytes(16))
            assert got == want, f"{tag}: pair slot {s} ({a - 1}, {b - 1}) VRAM != its halves"
            bound[t] = (a, b)
            continue
        g = v - 1
        assert g2s[g] == s + 1, f"{tag}: slot {s} -> glyph {g} -> {g2s[g] - 1}"
        assert got == _want(g, lang), f"{tag}: slot {s} (glyph {g}) VRAM != its glyph"
        bound[t] = g
    bg2 = _w(m, BG2_TILE_BUF, 28 * 64)
    shown = 0
    for i in range(0, 28 * 64, 2):
        t = (bg2[i] | bg2[i + 1] << 8) & 0x3FF
        if 640 <= t < 768 or t >= 896:
            assert t in bound, f"{tag}: row {i // 64} shows tile {t}, a free cell"
            shown += 1
    assert _w(m, TOFU, 1)[0] == 0, f"{tag}: glyphs printed as '?' (no cell)"
    lo, hi = (int.from_bytes(_w(m, a, 2), "little") for a in (LO, HI))
    assert lo >= hi, f"{tag}: cells still waiting for VRAM ({lo:#x}..{hi:#x})"
    return shown


def _enter(m, total):
    m.settle()
    m.press("A")                                   # the gate: "yes", in the menu's language
    m.wait(lambda: "/sd2snes/onboarding.bin" in m.fwlog(), frames=900, what="the tour's load")
    m.wait(lambda: m.has(f"1/{total}"), frames=1500, what="the tour's first card")
    m.step(30)


def _walk(t, lang_idx, lang):
    sd = t.sd(config=f"---\nOnboardingVersion: 0\nLanguage: {lang_idx}\n")
    m = t.menu(sd)
    total = 47                                     # the Mk.III's cards
    _enter(m, total)
    seen = 0
    for n in range(1, total + 1):
        m.wait(lambda: m.has(f"{n}/{total}"), frames=300, what=f"card {n}")
        m.step(20)
        seen += _check(m, f"{lang} card {n}", lang)
        if SHOTS:
            m.shot(Path(SHOTS) / f"{lang}_{n:02d}.png")
        if n < total:
            m.press("RIGHT")
            m.step(40)
    assert seen > total * 10, f"{lang}: only {seen} CJK cells on screen in the whole tour"
    m.press("RIGHT")                               # past the last card: "all set"
    m.wait(lambda: not m.has(f"{total}/{total}"), frames=300, what="the all-set screen")
    m.step(40)
    assert _check(m, f"{lang} all set", lang) > 10, "the all-set screen is not in CJK"
    if SHOTS:
        m.shot(Path(SHOTS) / f"{lang}_done.png")
    return m


def test_tour_in_japanese(t):
    _walk(t, LANG_JA, "ja")


def test_tour_in_chinese(t):
    _walk(t, LANG_ZH, "zh")


def test_language_card_switches_live(t):
    """The language card switches the whole tour as the bar moves -- into a CJK language,
    between the two (their glyphs 128+ are different sheets) and back to a Latin one."""
    sd = t.sd(config="---\nOnboardingVersion: 0\n")
    m = t.menu(sd)
    _enter(m, 47)
    langs = ["en", "ptbr", "es", "de", "fr", "it", "ru", "nl", "ja", "zh"]
    for k in range(1, 10):                         # down to Chinese, through Japanese
        m.press("DOWN")
        m.step(40)
        _check(m, f"down to {langs[k]}")
    m.press("UP")                                  # Chinese -> Japanese
    m.step(40)
    assert _check(m, "back up to ja", "ja") > 20
    if SHOTS:
        m.shot(Path(SHOTS) / "lang_card_ja.png")
    m.press("UP")
    m.step(40)
    _check(m, "back to nl")
    assert m.has("Taal"), m.text()
