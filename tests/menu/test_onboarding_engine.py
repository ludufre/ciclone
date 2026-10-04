"""The tour's engine (onboarding.bin), apart from what the cards say:

  * cards for one board only: a descriptor flagged ONB_FF_MK3ONLY is left out on a Mk.II and
    one flagged ONB_FF_MK2ONLY on a Mk.III, in both directions and out of the N/total counter,
    like a card whose parent option is off. The board is the ST_IS_MK2 byte the firmware
    publishes on every boot of a menu image;
  * the live font preview on the text outline and anti-aliasing cards: the bar remaps the
    font the tour itself is drawn with (Theme / On / Off), the two cards compose, leaving a
    card without A puts the saved font back;
  * the "and more" card the other way round: its items on top, the focused one's text under.

The tests find their cards in the descriptor table (onboarding_const.a65), never by number,
so a reordered tour keeps them valid. The emulated firmware is the Mk.III one (it publishes
is_mk2 = 0); the Mk.II side runs on a tour built with ST_IS_MK2 pointed at the GbcStretch byte
of the CFG block (a byte no card writes): set ONB_SIM_MK2=1 for that build, and the tests
set GbcStretch on the card to play the Mk.II. ONB_TREE = the tree the tour was built from
(default: the firmware tree) -- the strings and the table are read from it."""
import os
import re
import sys
from pathlib import Path

import ciclone as c

TREE = Path(os.environ.get("ONB_TREE") or c.SD2SNES)
SIM_MK2 = os.environ.get("ONB_SIM_MK2") == "1"
SHOTS = os.environ.get("ONB_SHOTS")          # a folder: screenshots of the cards tested
FRESH = "---\nOnboardingVersion: 0\n"

sys.path.insert(0, str(TREE / "snes" / "utils"))
import gen_onb_lang as onb  # noqa: E402
sys.path.pop(0)


# ---------------------------------------------------------------- the tour's tables
def _defines(path):
    """#define NAME value, value = $hex, decimal or a sum of those and names defined above
    (the Mk.II build points ST_IS_MK2 at CFG_ADDR+$01D4)."""
    out = {}
    term = r"(?:\$[0-9A-Fa-f]+|\d+|[A-Za-z_]\w*)"
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(rf"\s*#define\s+(\w+)\s+({term}(?:\s*\+\s*{term})*)(?![\w$])", line)
        if not m:
            continue
        total = 0
        for v in re.split(r"\s*\+\s*", m.group(2)):
            if v.startswith("$"):
                total += int(v[1:], 16)
            elif v.isdigit():
                total += int(v)
            elif v in out:
                total += out[v]
            else:
                break
        else:
            out[m.group(1)] = total
    return out


MEMMAP = _defines(TREE / "snes" / "onboarding" / "onb_memmap.i65")
MAIN = _defines(TREE / "snes" / "onboarding" / "onboarding_main.a65")
NCARDS = MAIN["ONB_NUM_CARDS"]
MORE_FIRST = MAIN["ONB_MORE_FIRST"]
MK3ONLY, MK2ONLY = MEMMAP["ONB_FF_MK3ONLY"], MEMMAP["ONB_FF_MK2ONLY"]
CFG_KEYS = {"CFG_SHOW_COVERS": "ShowCovers", "CFG_SHOW_GAME_INFO": "ShowGameInfo",
            "CFG_GAME_INFO_VIDEO": "GameInfoVideo", "CFG_ENABLE_MENU_MUSIC": "EnableMenuMusic",
            "CFG_ENABLE_CHEAT_OVERLAY": "EnableCheatOverlay"}


def _expr(e):
    e = e.strip().lstrip("!")
    if e in ("", "0"):
        return 0
    if re.fullmatch(r"\d+", e):
        return int(e)
    if e.startswith("ONB_"):
        return sum(MEMMAP[p.strip()] for p in e.split("+"))
    return e                                   # a CFG_* name


def feat_table():
    """[{dep, name, text, dep2, flags, opt, cfg}] in onb_feat_table order."""
    src = (TREE / "snes" / "onboarding" / "onboarding_const.a65").read_text(errors="replace")
    lines = src[src.index("onb_feat_table:"):].splitlines()[1:]
    rows, cur = [], None
    for raw in lines:
        line = raw.split(";")[0].strip()
        if not line:
            continue
        m = re.match(r"\.word\s+(.*)$", line)
        if m and cur is None:
            w = [x.strip() for x in m.group(1).split(",")]
            if len(w) != 6:
                break
            cur = {"dep": _expr(w[0]), "name": w[2], "text": w[3], "dep2": _expr(w[4]), "flags": _expr(w[5])}
            continue
        m = re.match(r"\.byt\s+(\w+)\s*,\s*(\w+)\s*:\s*\.word\s+(\S+)$", line)
        if m and cur is not None:
            cur["opt"] = MEMMAP[m.group(2)]
            cur["cfg"] = _expr(m.group(3))
            rows.append(cur)
            cur = None
            continue
        break
    return rows


FEATS = feat_table()
CARDS = FEATS[:NCARDS]


def card_of(opt, cfg=None):
    for i, f in enumerate(CARDS):
        if f["opt"] == opt and (cfg is None or f["cfg"] == cfg):
            return i
    raise c.MenuError(f"no card with option kind {opt} {cfg or ''}")


def otr(label, lang="en"):
    v = onb.STRINGS[label][onb.LANGS.index(lang)]
    return c.encode_menu_text(v if isinstance(v, str) else v[0])


def para(label, lang="en"):
    """A paragraph's lines as the screen decodes them (the button markup draws nothing)."""
    return [c.encode_menu_text(x.replace("[", "").replace("]", ""))
            for x in onb.STRINGS[label][onb.LANGS.index(lang)]]


def name_of(i):
    return otr(CARDS[i]["name"])


# ---------------------------------------------------------------- the tour's WRAM
def _onb_var(name):
    addr, labels = 0x7E0000, {}
    for line in (TREE / "snes" / "onboarding" / "onb_data.a65").read_text().splitlines():
        m = re.match(r"^(\w+)?\s*\.(byt|word)\s+(.*)$", line.split(";")[0])
        if not m:
            continue
        if m.group(1):
            labels[m.group(1)] = addr
        addr += (1 if m.group(2) == "byt" else 2) * len(m.group(3).split(","))
    return labels[name]


def var(m, name, size=1):
    return int.from_bytes(m.peek("wram", _onb_var(name) & 0xFFFF, size), "little")


# ---------------------------------------------------------------- walking the tour
def _config(extra=""):
    """Every parent option on: what the tour shows then is decided by the board alone."""
    cfg = FRESH + "".join(f"{k}: {'1' if k in ('ShowCovers', 'ShowGameInfo') else 'true'}\n"
                          for k in CFG_KEYS.values())
    return cfg + extra


HDR = re.compile(r"(\d+)/(\d+)\s*$")


def header(m):
    """(card name row, N, total) of the card on screen, or None."""
    row = m.screen()[1] if len(m.screen()) > 1 else ""
    h = HDR.search(row)
    return (row[:h.start()].strip(), int(h.group(1)), int(h.group(2))) if h else None


def enter_tour(m):
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question")))
    m.press("A")
    m.wait(lambda: "/sd2snes/onboarding.bin" in m.fwlog(), frames=900, what="a carga do tour")
    m.wait(lambda: header(m) is not None and header(m)[1] == 1, frames=1500, what="o primeiro card")
    m.step(30)


def goto(m, i):
    """Right until the header names card i (the cards in between keep their answers)."""
    want = name_of(i)
    for _ in range(NCARDS + 2):
        h = header(m)
        if h and h[0] == want:
            m.step(30)
            return h
        m.press("RIGHT")
        m.step(40)
    raise c.MenuError(f"card {i} ({want}) not reached\n{m.text()}")


def walk(m):
    """From the first card, Right through to "all set": the names shown and the totals."""
    seen, totals = [], set()
    for _ in range(NCARDS + 2):
        if m.has(otr("onb_ui_done_title")):
            return seen, totals
        h = header(m)
        if h and (not seen or seen[-1] != h[0]):
            seen.append(h[0])
            totals.add(h[2])
        m.press("RIGHT")
        m.step(40)
    raise c.MenuError(f"the tour did not end\n{m.text()}")


def shot(m, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        m.shot(Path(SHOTS) / f"{name}.png")


# ---------------------------------------------------------------- 1. cards per board
def _board_cards():
    mk3 = [i for i, f in enumerate(CARDS) if f["flags"] & MK3ONLY]
    mk2 = [i for i, f in enumerate(CARDS) if f["flags"] & MK2ONLY]
    if not mk3 and not mk2:
        raise c.Skip("no card carries ONB_FF_MK3ONLY / ONB_FF_MK2ONLY yet")
    return mk3, mk2


def _check_board(t, mk2):
    mk3_only, mk2_only = _board_cards()
    if mk2 and not SIM_MK2:
        raise c.Skip("the Mk.II side needs the tour built with ONB_SIM_MK2 (see the module doc)")
    hidden = mk3_only if mk2 else mk2_only
    shown = mk2_only if mk2 else mk3_only
    m = t.menu(t.sd(config=_config("GbcStretch: true\n" if mk2 else "")))
    if not mk2:
        assert m.psram(MEMMAP["ST_IS_MK2"], 1)[0] == 0, "the Mk.III firmware did not publish is_mk2"
    enter_tour(m)
    seen, totals = walk(m)
    assert totals == {NCARDS - len(hidden)}, (totals, NCARDS, hidden)
    assert len(seen) == NCARDS - len(hidden), seen
    for i in hidden:
        assert name_of(i) not in seen, (i, name_of(i), seen)
    for i in shown:
        assert name_of(i) in seen, (i, name_of(i), seen)
    # and back: B from "all set", then Left, walks the same cards, the flagged ones still out
    m.step(30)
    back = []
    for k in range(NCARDS + 2):
        m.press("B" if k == 0 else "LEFT")
        m.step(40)
        h = header(m)
        if h and (not back or back[-1] != h[0]):
            back.append(h[0])
        if h and h[1] == 1:
            break
    assert back == seen[::-1], (back, seen)
    m.close()


def test_board_cards_mk3(t):
    """Mk.III: the MK2ONLY cards are out (walking forward, back, and in the counter)."""
    _check_board(t, mk2=False)


def test_board_cards_mk2(t):
    """Mk.II (ST_IS_MK2 = 1): the MK3ONLY cards are out, the MK2ONLY ones in."""
    _check_board(t, mk2=True)


def test_board_flags_do_not_turn_the_hook_on(t):
    """$04/$08 in the flags byte say which board shows the card, they are no "yes" flags: a
    yes on a board-flagged yes/no card without ONB_FF_HOOK leaves the hook and the in-game
    buttons as they were."""
    mk2 = SIM_MK2
    flag = MK2ONLY if mk2 else MK3ONLY
    cands = [i for i, f in enumerate(CARDS) if f["flags"] & flag and not f["flags"] & 0x03
             and f["opt"] == MEMMAP["ONB_OPT_ONOFF"]]
    if not cands:
        raise c.Skip("no board-flagged yes/no card without ONB_FF_HOOK")
    i = cands[0]
    sd = t.sd(config=_config(("GbcStretch: true\n" if mk2 else "")
                             + "EnableIngameHook: false\nEnableIngameButtons: false\n"))
    m = t.menu(sd)
    enter_tour(m)
    goto(m, i)
    m.press("UP")                          # Yes is row 0
    m.step(10)
    m.press("A")
    m.step(40)
    m.press("START")
    m.wait(lambda: m.has("Test Game.sfc"), frames=1500, what="o browser de volta")
    m.close()
    cfg = (t.read(sd, "/sd2snes/config.yml") or b"").decode(errors="replace")
    key = re.search(rf'#define\s+{CARDS[i]["cfg"]}\s+\("(\w+)"\)',
                    (TREE / "src" / "cfg.h").read_text()).group(1)
    assert f"{key}: true" in cfg, (key, cfg)                     # the yes was kept...
    assert "EnableIngameHook: false" in cfg and "EnableIngameButtons: false" in cfg, cfg


# ---------------------------------------------------------------- 2. the font preview
def _pristine_font():
    src = (TREE / "snes" / "font.a65").read_text(errors="replace")
    vals = []
    for line in src[re.search(r"^font\s+\.byt", src, re.M).start():].splitlines():
        line = line.split(";")[0]
        if ".byt" not in line:
            if vals:
                break
            continue
        vals += [int(x.strip()[1:], 16) for x in line.split(".byt", 1)[1].split(",") if x.strip()]
    assert len(vals) >= 0x1000, len(vals)
    return bytes(vals[:0x1000])


FONT = _pristine_font()
AA_OFF, OL_OFF = 1, 2


def remap(bits):
    """The font's 4096 bytes as theme_font_pass leaves them (bit0 AA off, bit1 outline off)."""
    out = bytearray(FONT)
    for i in range(0, 0x1000, 2):
        lo, hi = out[i], out[i + 1]
        if bits & AA_OFF:
            hi &= ~lo & 0xFF
        if bits & OL_OFF:
            hi &= lo
        out[i + 1] = hi
    return bytes(out)


def vram_font(m):
    """The font as genfonts lays it in VRAM, read back into the 4096-byte 2bpp order, from
    BG2 (2bpp at word $4000, 16 words per character) and BG1 (4bpp at word $0000, 32)."""
    bg2 = m.peek("vram", 0x8000, 0x2000)
    bg1 = m.peek("vram", 0x0000, 0x4000)
    f2 = b"".join(bg2[32 * ch:32 * ch + 16] for ch in range(256))
    f1 = b"".join(bg1[64 * ch:64 * ch + 16] for ch in range(256))
    blank2 = all(not any(bg2[32 * ch + 16:32 * ch + 32]) for ch in range(256))
    blank1 = all(not any(bg1[64 * ch + 16:64 * ch + 64]) for ch in range(256))
    return f2, f1, blank2 and blank1


def font_is(m, bits):
    f2, f1, blank = vram_font(m)
    return f2 == f1 == remap(bits) and blank


def wait_font(m, bits, what):
    m.wait(lambda: font_is(m, bits), frames=240, what=f"a fonte {what}")


C_OUTLINE = card_of(MEMMAP["ONB_OPT_EDGE"], "CFG_TEXT_OUTLINE")
C_AA = card_of(MEMMAP["ONB_OPT_EDGE"], "CFG_TEXT_ANTIALIAS")


def test_font_preview_follows_the_bar(t):
    """Theme / On / Off on the outline card redraws the tour's own text that way; Left leaves
    the card without keeping it and the saved font comes back; A keeps it and the next card
    (anti-aliasing) composes its own preview over it; B from there drops only its own."""
    assert C_AA == C_OUTLINE + 1, "the two font cards are expected one after the other"
    sd = t.sd(config=_config("TextOutline: 0\nTextAntiAlias: 0\n"))
    m = t.menu(sd)
    enter_tour(m)
    assert var(m, "onb_font_ok") == 1, "the image's own font should be the pristine one"
    goto(m, C_OUTLINE)
    wait_font(m, 0, "intacta")
    shot(m, "outline_0_theme")
    m.press("DOWN")                        # On
    m.step(20)
    assert font_is(m, 0)
    shot(m, "outline_1_on")
    m.press("DOWN")                        # Off
    wait_font(m, OL_OFF, "sem contorno")
    shot(m, "outline_2_off")
    m.press("LEFT")                        # back, not kept
    m.wait(lambda: header(m) and header(m)[0] != name_of(C_OUTLINE), what="o card anterior")
    wait_font(m, 0, "salva de volta")
    m.step(30)
    m.press("RIGHT")
    m.wait(lambda: header(m) and header(m)[0] == name_of(C_OUTLINE), what="o card de contorno")
    m.step(30)
    wait_font(m, 0, "do valor salvo (Tema)")
    m.press("DOWN")
    m.step(10)
    m.press("DOWN")                        # Off...
    m.step(10)
    m.press("A")                           # ...kept
    m.wait(lambda: header(m) and header(m)[0] == name_of(C_AA), what="o card de suavizacao")
    m.step(30)
    wait_font(m, OL_OFF, "com o contorno gravado")
    shot(m, "aa_0_theme")
    m.press("DOWN")
    m.step(20)
    assert font_is(m, OL_OFF)
    shot(m, "aa_1_on")
    m.press("DOWN")                        # AA off too: both edges gone
    wait_font(m, OL_OFF | AA_OFF, "sem contorno e sem suavizacao")
    shot(m, "aa_2_off")
    m.press("B")                           # back to the outline card: its saved Off stays
    m.wait(lambda: header(m) and header(m)[0] == name_of(C_OUTLINE), what="o card de contorno")
    wait_font(m, OL_OFF, "so sem contorno")
    m.step(30)
    m.press("START")
    m.wait(lambda: m.has("Test Game.sfc"), frames=1500, what="o browser de volta")
    m.close()
    cfg = (t.read(sd, "/sd2snes/config.yml") or b"").decode(errors="replace")
    assert "TextOutline: 2" in cfg and "TextAntiAlias: 0" in cfg, cfg


def test_font_preview_from_a_remapped_font(t):
    """Saved Off: the firmware loads the tour with the font already remapped, and the pristine
    copy it keeps is what brings an edge back -- On on the outline card shows the outline."""
    m = t.menu(t.sd(config=_config("TextOutline: 2\nTextAntiAlias: 2\n")))
    enter_tour(m)
    assert var(m, "onb_font_ok") == 2, var(m, "onb_font_ok")
    assert var(m, "onb_font_boot") == 3
    goto(m, C_OUTLINE)
    m.wait(lambda: var(m, "onb_sel") == 2, what="a barra em Desligado")
    wait_font(m, OL_OFF | AA_OFF, "salva (sem as duas bordas)")
    m.press("UP")                          # On
    wait_font(m, AA_OFF, "com contorno, sem suavizacao")
    m.press("UP")                          # Theme: no theme, so the edge is on
    m.step(20)
    assert font_is(m, AA_OFF)
    m.close()


def _thm(flags):
    """A .thm that themes nothing but asks for these font-edge flags (src/theme.c header:
    magic, version 1, one region in slot 0 -- the font, which no theme writes -- of 0 bytes)."""
    return b"FXTHEME1" + bytes([1, 1]) + flags.to_bytes(2, "little") + bytes(4) + bytes(4)


def test_font_preview_theme_follows_the_thm(t):
    """A theme that turns the outline off: saved as Theme, the tour boots without it, reads
    that as the theme's, and Theme / On / Off on the card are off / on / off."""
    m = t.menu(t.sd(config=_config("TextOutline: 0\nTextAntiAlias: 0\nSkinName: \"/flat.thm\"\n"),
                    extra={"/flat.thm": _thm(0x0002)}))
    enter_tour(m)
    assert var(m, "onb_font_theme") == OL_OFF, var(m, "onb_font_theme")
    goto(m, C_OUTLINE)
    wait_font(m, OL_OFF, "do tema")
    m.press("DOWN")                        # On wins over the theme
    wait_font(m, 0, "com contorno")
    m.press("DOWN")
    wait_font(m, OL_OFF, "sem contorno")
    m.close()


# ---------------------------------------------------------------- 3. "and more"
C_MORE = card_of(MEMMAP["ONB_OPT_MORE"])


def test_more_card_items_on_top(t):
    """The items in their box right under the rule (the title on row 4), the focused item's
    paragraph one blank row under the box; Down changes the paragraph, not the list."""
    items = [i for i in range(MORE_FIRST, len(FEATS))]
    names = [otr(FEATS[i]["name"]) for i in items]
    rows_text = len(onb.STRINGS[FEATS[items[0]]["text"]][0])
    vis = max(1, min(len(items), MAIN["ONB_MORE_ROWS"] - rows_text))
    m = t.menu(t.sd(config=_config()))
    enter_tour(m)
    goto(m, C_MORE)
    scr = m.screen()
    assert otr("onb_ui_more").strip() in scr[4], scr[4]
    for k in range(vis):
        assert names[k] in scr[5 + k], (k, names[k], scr[5 + k])
    text_row = 5 + vis + 2
    lines = para(FEATS[items[0]]["text"])
    for k, line in enumerate(lines):
        assert line.strip() in scr[text_row + k] if line.strip() else True, (k, line, scr[text_row + k])
    assert text_row + len(lines) - 1 <= 24
    shot(m, "more_0")
    m.press("DOWN")
    m.wait(lambda: para(FEATS[items[1]]["text"])[0].strip() in m.screen()[text_row],
           what="o texto do 2o item")
    scr = m.screen()
    for k in range(vis):
        assert names[k] in scr[5 + k], (k, names[k], scr[5 + k])
    assert var(m, "onb_list_row") == 5 and var(m, "onb_list_vis") == vis
    # the bar is on the second item's row (HDMA colour math, blue added inside window 1)
    assert m.rgb(100, (5 + 1) * 8 + 3)[2] > m.rgb(100, (5 + 0) * 8 + 3)[2] + 40
    shot(m, "more_1")
    m.close()
