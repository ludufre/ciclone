"""Primeiro boot: o menu pergunta uma vez se o usuario quer ver o tour das novidades
(onboarding.bin, uma ROM separada que a firmware sobe NO LUGAR do menu). B pula para sempre,
A sobe o tour e o fim do tour volta ao menu com a versao do tour gravada (OnboardingVersion:
um release que acrescenta cards sobe a versao e o tour volta so com eles)."""
import sys

import ciclone as c

FRESH = "---\nOnboardingVersion: 0\n"
SEEN = "OnboardingVersion: 1"     # == ONB_VERSION


def _cfg(t, sd):
    return (t.read(sd, "/sd2snes/config.yml") or b"").decode(errors="replace")


def test_prompt_not_shown_when_done(t):
    m = t.menu(t.sd())
    assert not m.has(c.encode_menu_text(c.tr("text_onbg_question"))), m.text()


def test_prompt_not_shown_when_this_version_was_seen(t):
    """The gate asks while the version seen is below the tour's (ONB_VERSION = 1)."""
    m = t.menu(t.sd(config="---\n" + SEEN + "\n"))
    m.settle()
    assert not m.has(c.encode_menu_text(c.tr("text_onbg_question"))), m.text()


def test_prompt_language_and_skip(t):
    sd = t.sd(config=FRESH)
    m = t.menu(sd)
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question")))
    assert m.has("English"), m.text()
    m.press("RIGHT")
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question", "ptbr")))
    assert m.u8("cur_lang") == 1
    assert c.UNKNOWN not in m.text(), m.text()
    m.press("B")
    m.wait_gone(c.encode_menu_text(c.tr("text_onbg_question", "ptbr")))
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF
    assert "Test Game.sfc" in m.list_names()
    m.close()
    cfg = _cfg(t, sd)
    assert SEEN in cfg, cfg
    assert "Language: 1" in cfg, cfg


def test_prompt_missing_tour_counts_as_skip(t):
    sd = t.sd(config=FRESH, onboarding=False)
    m = t.menu(sd)
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question")))
    m.press("A")
    m.wait_gone(c.encode_menu_text(c.tr("text_onbg_question")))
    m.settle()
    assert "Test Game.sfc" in m.list_names()
    assert "onboarding.bin not found" in m.fwlog()
    m.close()
    assert SEEN in _cfg(t, sd)


NCARDS = 40         # card descriptors (onb_feat_table); the header counts the ones shown
MORE_CARD = 32      # "and more": the base tour's last card, 8 items
SECTION_CARD = 33   # the 2.17 section's opening card, then the release's cards (34..40)
MORE_ITEMS = 8
# the cards by descriptor number (onb_fN_name)
C_THEME, C_OUTLINE, C_AA, C_COVERS, C_COVLISTS, C_GI, C_VIDEO, C_CLIPMUSIC = 2, 3, 4, 5, 6, 7, 8, 9
C_MUSIC, C_RANDOM, C_SFX, C_MSU, C_PCM, C_SD2SNESDIR, C_RESET, C_CHEATLIST = 10, 11, 12, 13, 14, 15, 16, 17
C_IGM, C_STATES, C_SAVES, C_TRAINER, C_PATCHES, C_CREATEROM, C_CHIPS = 18, 19, 20, 21, 22, 23, 24
C_SUFAMI, C_CCTIME, C_CONSOLES, C_ATARI, C_FOLDERS, C_MEMTEST, C_LED = 25, 26, 27, 28, 29, 30, 31
C_PAD2, C_GBC, C_HOOKLIST, C_SETA, C_COL20, C_ICONS, C_GICHEATS = 34, 35, 36, 37, 38, 39, 40
# Cards shown on one board only (ONB_FF_MK3ONLY / ONB_FF_MK2ONLY): the Ciclone is a Mk.III,
# so the Mk.II's LED card is left out of every walk and of the header's count.
MK3ONLY = (C_CONSOLES, C_ATARI, C_GBC)
MK2ONLY = (C_LED,)
# cards a parent's off answer leaves out
NO_RANDOM = (C_RANDOM,)                  # menu music off
NO_COVLISTS = (C_COVLISTS,)              # box art off
NO_GI = (C_VIDEO, C_CLIPMUSIC)           # game info card off
NO_VIDEO = (C_CLIPMUSIC,)                # its video off
NO_IGM = (C_SAVES, C_TRAINER)            # in-game menu off


def shown(skip=()):
    """The descriptors the tour walks on the Mk.III, in order, minus `skip`."""
    return [n for n in range(1, NCARDS + 1) if n not in MK2ONLY and n not in skip]


def pos(n, skip=()):
    return shown(skip).index(n) + 1


def tot(skip=()):
    return len(shown(skip))


def hdr(n, skip=()):
    """The header's "N/total" on card n."""
    return f"{pos(n, skip)}/{tot(skip)}"


TOTAL = tot()

sys.path.insert(0, str(c.SD2SNES / "snes" / "utils"))
import gen_onb_lang as onb  # noqa: E402  the tour's own strings (not in the menu dicts)
sys.path.pop(0)


def otr(label, lang="en"):
    """A tour string as the screen decodes it."""
    return c.encode_menu_text(onb.STRINGS[label][onb.LANGS.index(lang)])


def para(n, lang="en", line=0):
    """A line of card n's paragraph (gen_onb_lang.py wraps it) as the screen decodes it."""
    raw = onb.STRINGS["onb_f%d_text" % n][onb.LANGS.index(lang)][line]
    return c.encode_menu_text(raw.replace("[", "").replace("]", ""))   # button markup draws nothing


def _enter_tour(m, lang="en", total=None):
    """Answer yes to the first-boot question and wait for the tour's first card (total =
    the cards the header counts, when the test leaves some out from the start)."""
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question", lang)))
    m.press("A")
    m.wait(lambda: "/sd2snes/onboarding.bin" in m.fwlog(), frames=900, what="a carga do tour")
    # the first card; "/12" when a card is left out (random music without music)
    m.wait(lambda: m.has(f"1/{total}") if total else (m.has(f"1/{TOTAL}") or m.has(f"1/{TOTAL - 1}")),
           frames=1500,
           what="o primeiro card do tour")
    m.step(30)                             # the card fades in; a press during the ramp is lost


def _goto_card(m, n, skip=()):
    """From a card before n (Right), until the header shows card n (`skip` = the cards
    left out by the answers given)."""
    for _ in range(NCARDS + 2):
        if m.has(hdr(n, skip)):
            m.step(30)
            return
        m.press("RIGHT")
        m.step(40)
    raise c.MenuError(f"card {n} not reached\n{m.text()}")


def _list_lit(m, first):
    """Blue of the answer list's row k (the bar is HDMA colour math, in no tilemap):
    the list sits right under the card's paragraph, so its rows are found from the
    first answer's label. Sampled right of the labels, inside the bar's window (the
    list is in the left column: lowres x 10..115)."""
    r0 = m.row_of(first)
    assert r0 is not None, m.text()
    return lambda k: m.rgb(100, (r0 + k) * 8 + 3)[2]


def _back_to_menu(m):
    m.wait(lambda: "m3nu.bin" in m.fwlog().split("/sd2snes/onboarding.bin")[-1],
           frames=900, what="o menu recarregado")
    m.wait(lambda: m.has("Test Game.sfc"), frames=900, what="o browser")
    m.settle()


def test_tour_runs_and_returns_to_menu(t):
    """START on a card ends the tour right there: back to the menu, flag saved."""
    sd = t.sd(config=FRESH)
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, 1)
    m.press("START")
    _back_to_menu(m)
    assert not m.has(hdr(1)), m.text()
    m.close()
    assert SEEN in _cfg(t, sd)


def test_tour_answers_are_saved(t):
    """A list per card, the menu's bar on the focused answer: Up/Down move it (and stop
    at the ends), A keeps the focused answer and goes on to the next card. Going back
    with Left keeps the old value. The "all set" screen's A saves config.yml."""
    sd = t.sd(config=FRESH + "ShowCovers: 1\nEnableMenuMusic: true\nMenuMusicRandom: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_COVERS)                # box art: Off / Large / Small, bar on Large
    m.press("DOWN")                        # -> Small
    m.step(10)
    m.press("DOWN")                        # the last one: stays
    m.step(10)
    m.press("A")                           # keep Small, next card
    m.wait_text(hdr(C_COVLISTS))
    _goto_card(m, C_MUSIC)                 # menu music: Yes / No, bar on Yes
    m.press("DOWN")
    m.step(10)
    m.press("A")                           # keep No: random music is left out
    m.wait_text(hdr(C_SFX, NO_RANDOM))     # the menu sounds card takes its place
    assert m.has(otr(f"onb_f{C_SFX}_name")), m.text()
    m.step(30)
    m.press("LEFT")                        # back skips it too
    m.wait_text(hdr(C_MUSIC, NO_RANDOM))
    assert m.has(otr(f"onb_f{C_MUSIC}_name")), m.text()
    m.step(30)
    m.press("RIGHT")
    m.wait_text(hdr(C_SFX, NO_RANDOM))
    m.step(30)
    m.press("DOWN")                        # menu sounds: moved but not kept...
    m.step(10)
    m.press("LEFT")                        # ...going back leaves it as it was
    m.wait_text(hdr(C_MUSIC, NO_RANDOM))
    m.step(30)
    m.press("RIGHT")                       # the bar sits on the kept answers again
    m.wait_text(hdr(C_SFX, NO_RANDOM))
    m.step(30)
    for _ in range(NCARDS + 2):            # Right past the last card
        if m.has(otr("onb_ui_done_title")):
            break
        m.press("RIGHT")
        m.step(40)
    m.wait_text(otr("onb_ui_done_title"))
    m.step(30)
    m.press("A")
    _back_to_menu(m)
    m.close()
    cfg = _cfg(t, sd)
    for want in ("ShowCovers: 2", "EnableMenuMusic: false", "MenuMusicRandom: true",
                 "EnableMenuSFX: true", SEEN):
        assert want in cfg, (want, cfg)


def test_tour_has_no_guides_card(t):
    """The guides are always on with the in-game menu: no tour card asks about them, and the
    in-game menu card is followed by the savestates card."""
    assert not any("Guides" in onb.STRINGS["onb_f%d_name" % n][0] for n in range(1, NCARDS + 1))
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, C_IGM)
    assert m.has(otr(f"onb_f{C_IGM}_name")), m.text()
    m.press("A")
    m.wait_text(hdr(C_STATES))
    assert m.has(otr(f"onb_f{C_STATES}_name")), m.text()
    m.step(30)
    m.press("A")
    m.wait_text(hdr(C_SAVES))
    m.close()

def test_tour_demo_follows_the_focus(t):
    """The demo picture streams into the hidden VRAM slot and the 16 sprites swap to
    it: moving the bar on the box-art card flips them from slot 0 (name table 0, OBJ
    palettes 0-3) to slot 1 (table 1, palettes 4-7), and back."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, C_COVERS)
    oam = m.peek("oam", 0, 4)
    slot = lambda: m.peek("oam", 0, 4)[3] & 0x01
    pal = lambda: m.peek("oam", 0, 4)[3] >> 1 & 7
    assert oam[0] == 128 and oam[1] == 31 and slot() == 0 and pal() < 4, oam.hex()  # ONB_DEMO_X/Y
    m.press("DOWN")
    m.wait(lambda: slot() == 1 and pal() >= 4, what="o slot 1 na tela")
    m.press("UP")
    m.wait(lambda: slot() == 0 and pal() < 4, what="o slot 0 de volta")


def test_tour_language_card_flag_follows_the_focus(t):
    """On the language card the flag picture follows the bar like any other demo:
    Down swaps the demo to the other VRAM slot (the next language's flag)."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, 1)
    slot = lambda: m.peek("oam", 0, 4)[3] & 0x01
    before = slot()
    m.press("DOWN")
    m.wait(lambda: slot() != before, what="a bandeira do idioma seguinte")
    m.step(30)
    m.press("UP")
    m.wait(lambda: slot() == before, what="a bandeira de volta")


def test_tour_and_more_card(t):
    """The base tour's last card lists the info-only novelties; moving the bar shows
    each one's text (and its demo). The eight items are all listed at once, no scroll bar.
    A goes on to the 2.17 section."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, MORE_CARD)
    assert m.has(otr(f"onb_f{MORE_CARD}_name")), m.text()          # "And more"
    first = NCARDS + 1                                              # its items: after the cards
    last = first + MORE_ITEMS - 1
    assert m.has(para(first)), m.text()                            # item 1's text
    for n in range(first, last + 1):
        assert m.has(otr(f"onb_f{n}_name")), (n, m.text())         # every item listed
    assert not [r for r in range(28) if m.tile_at(29, r)[0] == 17], m.text()   # no thumb
    for n in range(first + 1, last + 1):
        m.press("DOWN")
        m.wait_text(para(n))                                       # its text
        m.step(12)
    assert m.has(otr(f"onb_f{first}_name")), m.text()              # nothing scrolled away
    m.press("A")
    m.wait_text(hdr(SECTION_CARD))


def test_tour_217_section(t):
    """After the base tour, a card opens the 2.17 section, then the release's cards:
    controller 2, Game Boy Color, the in-game shortcut list, the community cartridges,
    the browser icons, cheats from the game info card; then "all set"."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, SECTION_CARD)
    assert m.has(otr(f"onb_f{SECTION_CARD}_name")), m.text()      # "What's new in 2.17"
    assert m.has(para(SECTION_CARD)), m.text()
    for n in [k for k in shown() if k > SECTION_CARD]:
        m.press("RIGHT")
        m.wait_text(hdr(n))
        assert m.has(otr(f"onb_f{n}_name")), (n, m.text())
        m.step(30)
    m.press("RIGHT")
    m.wait_text(otr("onb_ui_done_title"))


def test_tour_footer_is_left_aligned(t):
    """The key hints start at the left edge on every card: a card with nothing to choose
    drops the up/down hint and the others move into its place (no hole at the start)."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    nxt = c.encode_menu_text(onb.STRINGS["onb_ui_next"][0])
    for n in (C_COVERS, SECTION_CARD):     # a card with answers, an info-only card
        _goto_card(m, n)
        m.step(30)
        foot = m.screen()[27]
        assert nxt in foot, (n, foot)
        assert foot[:2].strip(), (n, foot)  # something at columns 0..1
        m.step(10)
    m.close()


def test_tour_done_screen_key_is_green(t):
    """"PRESS A FOR THE MENU": the A is green like every key hint, the words are not --
    in English and in German, where the line starts with the key."""
    for lang, idx in (("en", 0), ("de", 3)):
        m = t.menu(t.sd(config=FRESH + "Language: %d\n" % idx))
        _enter_tour(m, lang)
        _goto_card(m, NCARDS)
        m.press("RIGHT")
        m.wait_text(otr("onb_ui_done_title", lang))
        m.step(30)
        line = c.encode_menu_text(onb.STRINGS["onb_ui_done_go"][onb.LANGS.index(lang)])
        row = m.row_of(line)
        assert row is not None, m.text()
        x0 = m.screen()[row].index(line)
        k = line.index("A ") if line.startswith("A ") else line.index(" A") + 1
        assert m.tile_at(x0 + k, row)[1] == 2, (lang, m.tile_at(x0 + k, row))
        other = next(i for i, ch in enumerate(line) if ch not in " A")
        assert m.tile_at(x0 + other, row)[1] == 0, (lang, other)
        m.close()


def test_tour_buttons_in_the_text_are_green(t):
    """A button named in a card's paragraph is green like the key hints, the '+' between
    two of them is not: L+R+Y+Left on the in-game menu card, in English and Portuguese."""
    for lang, idx in (("en", 0), ("ptbr", 1)):
        m = t.menu(t.sd(config=FRESH + "Language: %d\n" % idx))
        _enter_tour(m, lang)
        _goto_card(m, C_IGM)
        m.step(30)
        lines = onb.STRINGS[f"onb_f{C_IGM}_text"][onb.LANGS.index(lang)]
        k = next(i for i, l in enumerate(lines) if "[L]+[R]" in l)
        raw = lines[k]
        plain = raw.replace("[", "").replace("]", "")
        row = m.row_of(c.encode_menu_text(plain))
        assert row is not None, m.text()
        x0 = m.screen()[row].index(c.encode_menu_text(plain))
        col, green, x = {}, False, 0
        for ch in raw:                     # expected colour of every printed cell
            if ch in "[]":
                green = not green
                continue
            col[x] = green
            x += 1
        for i, want in col.items():
            if plain[i] == " ":
                continue
            pal = m.tile_at(x0 + i, row)[1]
            assert (pal == 2) == want, (lang, plain, i, plain[i], pal)
        m.close()


def test_tour_names_no_authors(t):
    """Credits live in the README and on the landing, never in the tour: no card name or
    paragraph, in any language, names the community cartridges' authors."""
    for key, cols in onb.STRINGS.items():
        for k, col in enumerate(cols):
            text = " ".join(col) if isinstance(col, (list, tuple)) else col
            for who in ("M2M", "terminator2k2", "sttng"):
                assert who not in text, (key, k, who)


def test_tour_keeps_the_boot_intro(t):
    """The power-on screen is not a tour card (only the settings turn it off): walking the
    whole tour keeps BootIntro as it was, and the screen does not play again when the tour
    hands back to the menu (a menu reload is not a power-on)."""
    sd = t.sd(config=FRESH + "BootIntro: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, NCARDS)
    m.press("RIGHT")
    m.wait_text(otr("onb_ui_done_title"))
    m.step(30)
    m.press("A")
    start = m.frame
    _back_to_menu(m)
    assert m.frame - start < 200, m.frame - start
    m.close()
    assert "BootIntro: true" in _cfg(t, sd), _cfg(t, sd)

# the menu's silent S-DSP stub (snes/sfxdsp.i65), as the APU holds it at $0200: with the
# music off the S-SMP runs it (the console gates the cart's MSU-1 DAC otherwise)
STUB = bytes([0x8F, 0x6C, 0xF2, 0x8F, 0x60, 0xF3])


def test_tour_without_music_runs_the_silent_stub(t):
    """Menu music off: the tour does what the menu does -- the S-SMP runs the silent
    S-DSP stub, not nothing (the menu sounds need it on the console)."""
    m = t.menu(t.sd(config=FRESH + "EnableMenuMusic: false\n"))
    _enter_tour(m)
    m.wait(lambda: m.peek("aram", 0x200, 6) == STUB, what="o stub do S-DSP")


def test_tour_music_follows_the_music_card(t):
    """The tour plays the menu's music (CMD_LOAD_MENU_SPC + the menu's own uploader);
    on the menu music card No stops it and Yes plays it again -- each a console reset
    (the S-SMP only takes a new program from its IPL), back on the same card: No
    leaves the silent stub in the APU, Yes the music."""
    spc = (c.SD2SNES / "misc" / "music" / "28.spc").read_bytes()
    m = t.menu(t.sd(config=FRESH + "EnableMenuMusic: true\nMenuMusicRandom: false\n",
                    extra={"/sd2snes/menu.spc": spc}))
    _enter_tour(m)
    tour_log = lambda: m.fwlog().split("/sd2snes/onboarding.bin")[-1]
    m.wait(lambda: "cmd: 30" in tour_log(), frames=600, what="o tour pedir a musica")
    assert "file_open (/sd2snes/menu.spc, 01): FR_OK" in tour_log()
    _goto_card(m, C_MUSIC)
    m.press("DOWN")                                   # No: the music stops
    m.wait(lambda: "RESET requested by SNES" in tour_log(), frames=600, what="o reset")
    m.wait_text(hdr(C_MUSIC), frames=1500)             # back on the same card
    lit = _list_lit(m, "Yes")                          # the list sits under the text
    m.wait(lambda: lit(1) > lit(0) + 40, what="No focado de volta")
    m.wait(lambda: m.peek("aram", 0x200, 6) == STUB, what="o stub do S-DSP")  # the silent stub
    m.step(30)
    m.press("UP")                                     # Yes: another reset, the music again
    m.wait(lambda: tour_log().count("RESET requested by SNES") >= 2, frames=600,
           what="o reset da volta")
    m.wait(lambda: tour_log().split("RESET requested by SNES")[-1].count("cmd: 30") > 0,
           frames=900, what="a musica de novo")
    m.wait(lambda: m.peek("aram", 0x200, 6) != STUB, frames=900, what="a musica na APU")


def _sfx_count(m, since):
    """Effects the firmware let through (it logs "sfx N" for each, N = effect+1)."""
    return m.fwlog()[since:].count("sfx ")


def test_tour_plays_the_menu_sounds(t):
    """With the menu sounds on, the tour sends the menu's effects: paging is a cursor
    blip (1), A a confirm (2)."""
    m = t.menu(t.sd(config=FRESH + "EnableMenuSFX: true\n"))
    _enter_tour(m)
    n = len(m.fwlog())
    m.press("RIGHT")
    m.wait(lambda: "sfx 1" in m.fwlog()[n:], what="o bip do cursor")
    m.step(40)
    m.press("A")
    m.wait(lambda: "sfx 2" in m.fwlog()[n:], what="o bip de confirmar")


def test_tour_sound_reaches_the_dac(t):
    """End to end: the tour's cursor blip makes the firmware preload
    /sd2snes/sfx_cursor.pcm into the PSRAM and start the FPGA's SFX fetcher on its
    PCM body (what the cart's DAC plays)."""
    pcm = (c.SD2SNES / "misc" / "sfx_cursor.pcm").read_bytes()
    m = t.menu(t.sd(config=FRESH + "EnableMenuSFX: true\n",
                    extra={"/sd2snes/sfx_cursor.pcm": pcm}))
    _enter_tour(m)
    m.press("RIGHT")
    m.wait(lambda: m.sfx()[1] > 0, what="o SFX no fetcher")
    base, ln = m.sfx()
    assert ln == len(pcm) - 8, (hex(ln), len(pcm))          # the body: the file minus "MSU1"+loop
    assert m.peek("psram", base, 32) == pcm[8:40]


def test_tour_sounds_card_previews_and_undoes(t):
    """Menu sounds off: the tour is quiet; on the sounds card, focusing Yes previews
    them (a blip gets through), and leaving the card without A puts the saved "No"
    back -- quiet again, and config.yml keeps it."""
    sd = t.sd(config=FRESH + "EnableMenuSFX: false\nEnableMenuMusic: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    n = len(m.fwlog())
    _goto_card(m, C_SFX)
    assert m.has(otr(f"onb_f{C_SFX}_name")), m.text()
    assert _sfx_count(m, n) == 0, m.fwlog()[n:]
    m.press("UP")                              # Yes: the preview
    m.wait(lambda: _sfx_count(m, n) > 0, what="a previa do som")
    m.step(40)
    m.press("LEFT")                            # left without answering
    m.wait_text(hdr(C_RANDOM))
    m.step(40)
    k = len(m.fwlog())
    m.press("DOWN")
    m.step(40)
    m.press("LEFT")
    m.step(60)
    assert _sfx_count(m, k) == 0, m.fwlog()[k:]
    m.press("START")
    _back_to_menu(m)
    m.close()
    assert "EnableMenuSFX: false" in _cfg(t, sd)


def test_tour_music_comes_back_when_its_card_is_left(t):
    """No on the music card stops it (a reset); leaving the card without A puts the
    saved "Yes" back: the next card plays it again."""
    spc = (c.SD2SNES / "misc" / "music" / "28.spc").read_bytes()
    m = t.menu(t.sd(config=FRESH + "EnableMenuMusic: true\nMenuMusicRandom: false\n",
                    extra={"/sd2snes/menu.spc": spc}))
    _enter_tour(m)
    tour_log = lambda: m.fwlog().split("/sd2snes/onboarding.bin")[-1]
    _goto_card(m, C_MUSIC)
    m.press("DOWN")
    m.wait(lambda: "RESET requested by SNES" in tour_log(), frames=600, what="o reset")
    m.wait_text(hdr(C_MUSIC), frames=1500)
    m.step(30)
    after = lambda: tour_log().split("RESET requested by SNES")[-1].count("cmd: 30")
    before = after()
    m.press("LEFT")                            # left without answering
    m.wait(lambda: after() > before, frames=600, what="a musica de volta")


def test_tour_right_keeps_the_focused_answer(t):
    """Right keeps the focused answer like A: the bar on "No" over the music card and
    Right leads past the random music card (it depends on the music) to the sounds card,
    and the music stays off."""
    sd = t.sd(config=FRESH + "EnableMenuMusic: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_MUSIC)
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("RIGHT")
    m.wait_text(hdr(C_SFX, NO_RANDOM))     # the menu sounds card, random music left out
    assert m.has(otr(f"onb_f{C_SFX}_name")), m.text()
    m.step(30)
    m.press("START")
    _back_to_menu(m)
    m.close()
    assert "EnableMenuMusic: false" in _cfg(t, sd), _cfg(t, sd)


def test_tour_language_card_switches_live(t):
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, 1)
    assert m.has(otr("onb_f1_name")), m.text()
    m.press("DOWN")                        # English -> Portugues, the whole tour follows
    m.wait_text(otr("onb_f1_name", "ptbr"))
    # the bar (HDMA colour math, not in any tilemap) followed: row 1 of the list is lit,
    # row 0 is not. Sampled right of the labels, inside the bar's window.
    lit = _list_lit(m, "English")
    m.wait(lambda: lit(1) > lit(0) + 40, what="a barra na linha 1")
    m.press("A")
    m.wait_text(hdr(2))


def test_tour_opens_on_the_first_card_and_back_stays(t):
    """No opening screen: the tour starts on its first card, and B there does nothing."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    assert m.has(otr("onb_f1_name")), m.text()
    m.press("B")
    m.step(60)
    assert m.has(hdr(1)), m.text()


def _tour_in(t, idx):
    """Every card of the tour, and the "all set" screen, draw in language idx with no
    unknown glyph (a character outside the font's ACCENTS/HOMOGLYPHS turns into garbage
    silently)."""
    lang = c.LANGS[idx]
    m = t.menu(t.sd(config=f"---\nLanguage: {idx}\nOnboardingVersion: 0\n"))
    _enter_tour(m, lang)
    for n in shown():
        _goto_card(m, n)
        assert c.UNKNOWN not in m.text(), f"{lang}: card {n}\n{m.text()}"
    m.press("RIGHT")
    m.wait(lambda: not m.has(hdr(NCARDS)), what="a tela final")
    m.step(30)
    assert c.UNKNOWN not in m.text(), f"{lang}: final\n{m.text()}"


for _i, _lang in enumerate(c.LANGS):
    def _mk(i):
        def test(t):
            _tour_in(t, i)
        return test
    _fn = _mk(_i)
    _fn.__name__ = f"test_tour_language_{_i}_{_lang}"
    _fn.__module__ = __name__
    globals()[_fn.__name__] = _fn


def _open_tour_entry(m):
    """Main menu (X) > Settings > the last row, "Tour of the new features"."""
    m.press("X")
    m.wait_text(c.tr("mtext_mm_cfg"))
    for _ in range(12):
        if c.encode_menu_text(c.tr("mtext_mm_cfg")) in m.bar_row():
            break
        m.press("DOWN")
        m.step(4)
    m.press("A")
    m.wait_text(c.tr("mtext_cfg_patch"))
    for _ in range(14):
        if c.encode_menu_text(c.tr("mtext_cfg_tour")) in m.bar_row():
            break
        m.press("DOWN")
        m.step(4)
    assert c.encode_menu_text(c.tr("mtext_cfg_tour")) in m.bar_row(), m.text()
    m.press("A")


def test_settings_entry_replays_tour(t):
    sd = t.sd()                                    # already onboarded -- no prompt
    m = t.menu(sd)
    _open_tour_entry(m)
    m.wait_text(hdr(1), frames=1500)               # the whole tour, from its first card
    m.step(30)
    m.press("START")
    m.wait(lambda: m.has("Test Game.sfc"), frames=1500, what="o browser de volta")
    m.close()
    assert SEEN in _cfg(t, sd)


def test_settings_entry_without_tour_shows_popup(t):
    m = t.menu(t.sd(onboarding=False))
    _open_tour_entry(m)
    m.wait_text(c.tr("text_err_supplfile"), frames=900)
    assert m.has("onboarding.bin"), m.text()
    m.press("A")
    m.wait_gone(c.tr("text_err_supplfile"))
    m.settle()
    assert m.has(c.tr("mtext_cfg_tour")), m.text()   # still in Settings


# ---------------------------------------------------------------- the welcome clip
# After the gate's yes the tour plays misc/welcome.fmv (video staged by the firmware in
# PSRAM) with misc/welcome.pcm (streamed to the MSU-1 DAC), then opens on its first card.
# The tour has no symbol map in the package: its WRAM variables are found from the data
# segment's source (onb_data.a65: consecutive .byt/.word; the linker puts the segment at
# $7E0000 -- its `*= $7E0100` is not honoured).

def _onb_var(name):
    import re
    addr, labels = 0x7E0000, {}
    for line in (c.SD2SNES / "snes" / "onboarding" / "onb_data.a65").read_text().splitlines():
        m = re.match(r"^(\w+)?\s*\.(byt|word)\s+(.*)$", line.split(";")[0])
        if not m:
            continue
        if m.group(1):
            labels[m.group(1)] = addr
        addr += (1 if m.group(2) == "byt" else 2) * len(m.group(3).split(","))
    return labels[name]


def _wel(m, name, size=1):
    b = m.peek("wram", _onb_var(name) & 0xFFFF, size)
    return int.from_bytes(b, "little")


def _into_welcome(m):
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question")))
    m.press("A")
    m.wait(lambda: "welcome.fmv" in m.fwlog(), frames=1500, what="o clipe carregado")
    m.wait(lambda: _wel(m, "onb_wel_on") == 1, frames=600, what="o clipe tocando")


def test_welcome_clip_plays_after_the_gate(t):
    """The whole clip on NTSC time: every frame flipped on its 3rd VBlank (110 frames,
    330 VBlanks), every VBlank's DMA done inside the VBlank (the line it ended on stays
    below 262), the jingle on the DAC meanwhile; then the tour's first card."""
    m = t.menu(t.sd(config=FRESH, misc=True))
    _into_welcome(m)
    assert m.dac_playing(), "the jingle is not on the DAC"
    m.step(60)
    assert 12 <= _wel(m, "onb_wel_fi") <= 25, _wel(m, "onb_wel_fi")
    m.wait(lambda: _wel(m, "onb_wel_on") == 0, frames=900, what="o fim do clipe")
    assert _wel(m, "onb_wel_fi") == 110
    assert 330 <= _wel(m, "onb_wel_vbl", 2) <= 336, _wel(m, "onb_wel_vbl", 2)
    vmax = _wel(m, "onb_wel_vmax", 2)
    assert 225 <= vmax < 262, hex(vmax)
    assert not m.dac_playing(), "the jingle's DAC was not released"
    m.wait(lambda: m.has(f"1/{TOTAL}") or m.has(f"1/{TOTAL - 1}"), frames=900, what="o primeiro card")
    m.close()


def test_welcome_clip_skip(t):
    """B during the clip: the jingle stops at once, the picture fades, the tour goes on."""
    m = t.menu(t.sd(config=FRESH, misc=True))
    _into_welcome(m)
    m.step(20)
    m.press("B")
    m.wait(lambda: not m.dac_playing(), frames=120, what="o jingle parado")
    m.wait(lambda: _wel(m, "onb_wel_on") == 0, frames=120, what="o fim do clipe")
    assert _wel(m, "onb_wel_fi") < 40
    m.wait(lambda: m.has(f"1/{TOTAL}") or m.has(f"1/{TOTAL - 1}"), frames=900, what="o primeiro card")
    # the next menu blip plays through the DAC: what the cut jingle left in its buffer
    # must not come back with it (the FPGA's effect engine overwrites the buffer)
    m.step(60)
    for _ in range(4):
        if "sfx 1" in m.fwlog():
            break
        m.press("DOWN")
        m.step(30)
    assert "sfx 1" in m.fwlog(), m.fwlog()[-1500:]
    m.step(30)
    assert m.dac_loud() == 0, "the cut jingle loops on the DAC"
    m.close()


def test_welcome_clip_then_the_menu_music(t):
    """The clip runs the silent S-DSP stub (the console passes the cart's DAC only with
    the S-DSP running); with menu music on, the tour resets the console to get the
    S-SMP back to its IPL and comes back on its first card with the music."""
    spc = (c.SD2SNES / "misc" / "menu.spc").read_bytes()
    m = t.menu(t.sd(config=FRESH + "EnableMenuMusic: true\n", misc=True))
    _into_welcome(m)
    m.press("START")
    m.wait(lambda: m.has(f"1/{TOTAL}") or m.has(f"1/{TOTAL - 1}"),
           frames=1500, what="o primeiro card")
    m.wait(lambda: "file_open (/sd2snes/menu.spc, 01): FR_OK" in m.fwlog().split("welcome.fmv")[-1],
           frames=600, what="a música do menu depois do reset")
    assert "RESET requested by SNES" in m.fwlog().split("welcome.fmv")[-1]
    m.close()


def test_welcome_clip_on_replay(t):
    """The Settings entry replays the tour with the clip too; the tour's own music
    reset afterwards comes back on the first card without playing it again."""
    m = t.menu(t.sd(config="---\n" + SEEN + "\n", misc=True))
    m.settle()
    m.step(120)                            # the menu music's upload holds the pad
    _open_tour_entry(m)
    m.wait(lambda: _wel(m, "onb_wel_on") == 1, frames=1500, what="o clipe tocando")
    assert m.dac_playing(), "the jingle is not on the DAC"
    m.wait(lambda: m.has(f"1/{TOTAL}") or m.has(f"1/{TOTAL - 1}"),
           frames=1500, what="o primeiro card")
    m.step(120)
    assert m.fwlog().count("file_open (/sd2snes/welcome.fmv") == 1, "the clip played twice"
    m.close()


def test_tour_end_keeps_the_menu_music(t):
    """Ending the tour hands the console to the menu WITHOUT a reset: the S-SMP keeps
    the music it plays (no second menu.spc load, BGM_STATE 1 = playing) and the menu
    consumed the firmware's handoff byte ($2BE1)."""
    spc = (c.SD2SNES / "misc" / "menu.spc").read_bytes()
    sd = t.sd(config=FRESH + "EnableMenuMusic: true\n", extra={"/sd2snes/menu.spc": spc})
    m = t.menu(sd)
    _enter_tour(m)
    m.wait(lambda: "file_open (/sd2snes/menu.spc, 01): FR_OK" in m.fwlog().split("/sd2snes/onboarding.bin")[-1],
           frames=900, what="a música no tour")
    m.step(60)
    m.press("START")
    _back_to_menu(m)
    after = m.fwlog().split("cmd: 74")[-1]
    assert "RESET requested" not in after, after[-1500:]
    assert "/sd2snes/menu.spc" not in after, "the menu loaded the music again"
    assert m.peek("snescmd", 0x2F7, 1)[0] == 1, "BGM_STATE"
    assert m.peek("snescmd", 0x3E1, 1)[0] == 0, "MENU_HANDOFF not consumed"
    m.close()
    assert SEEN in _cfg(t, sd)


def test_tour_on_controller_2(t):
    """The whole tour on CONTROLLER 2 only, like the menu (read_pad merges both pads): the
    gate, skipping the welcome clip, paging the cards and answering one. Controller 1 stays
    idle throughout."""
    sd = t.sd(config=FRESH + "ShowCovers: 1\n", misc=True)
    m = t.menu(sd)
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question")))
    m.press("A", pad=2)                            # gate: yes
    m.wait(lambda: _wel(m, "onb_wel_on") == 1, frames=1500, what="o clipe tocando")
    m.step(20)
    m.press("B", pad=2)                            # skip the clip
    m.wait(lambda: _wel(m, "onb_wel_on") == 0, frames=120, what="o clipe pulado")
    m.wait(lambda: m.has(hdr(1)), frames=900, what="o primeiro card")
    m.step(30)
    for _ in range(12):                            # page to the box art card; like _goto_card,
        if m.has(hdr(C_COVERS)):                   # a press right after the fade can be lost
            break
        m.press("RIGHT", pad=2)
        m.step(40)
    assert m.has(hdr(C_COVERS)), m.text()
    m.step(30)
    m.press("DOWN", pad=2)                         # Large -> Small
    m.step(10)
    m.press("A", pad=2)                            # keep it
    m.wait_text(hdr(C_COVLISTS))
    m.step(30)
    m.press("START", pad=2)                        # end the tour
    _back_to_menu(m)
    m.close()
    cfg = _cfg(t, sd)
    assert "ShowCovers: 2" in cfg and SEEN in cfg, cfg


# ---------------------------------------------------------------- the base tour's newer cards

def _finish(m):
    """START on a card: the tour ends there, keeping every answer given."""
    m.step(30)
    m.press("START")
    _back_to_menu(m)


def test_tour_font_edge_cards_save(t):
    """Text outline and anti-aliasing: Theme / On / Off, in the menu's kv_text_edge order
    (0 / 1 / 2); the bar starts on the saved value and A keeps the focused one."""
    sd = t.sd(config=FRESH)
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_OUTLINE)
    assert m.has(otr(f"onb_f{C_OUTLINE}_name")), m.text()
    lit = _list_lit(m, otr("onb_text_theme"))
    m.wait(lambda: lit(0) > lit(1) + 40, what="a barra em Tema")
    m.press("DOWN")
    m.step(10)
    m.press("DOWN")                        # -> Off
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_AA))
    assert m.has(otr(f"onb_f{C_AA}_name")), m.text()
    m.step(30)
    m.press("DOWN")                        # -> On
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_COVERS))
    _finish(m)
    m.close()
    cfg = _cfg(t, sd)
    assert "TextOutline: 2" in cfg and "TextAntiAlias: 1" in cfg, cfg


def test_tour_covers_in_lists_depends_on_box_art(t):
    """Covers in Recent/Favorites is asked only with the box art on: Off on the box art
    card leaves it out; with covers on, its No is saved."""
    m = t.menu(t.sd(config=FRESH + "ShowCovers: 1\n"))
    _enter_tour(m)
    _goto_card(m, C_COVERS)
    m.press("UP")                          # Large -> Off
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_GI, NO_COVLISTS))    # the game info card takes its place
    assert m.has(otr(f"onb_f{C_GI}_name")), m.text()
    m.close()
    sd = t.sd(config=FRESH + "ShowCovers: 1\nShowCoversInLists: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_COVLISTS)
    assert m.has(otr(f"onb_f{C_COVLISTS}_name")), m.text()
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_GI))
    _finish(m)
    m.close()
    assert "ShowCoversInLists: false" in _cfg(t, sd), _cfg(t, sd)


def test_tour_video_cards_depend_on_the_game_info(t):
    """The clip card needs the game info card, its music card needs both: game info Off
    leaves the two out; the video's No leaves the music out and is saved."""
    m = t.menu(t.sd(config=FRESH + "ShowGameInfo: 1\n"))
    _enter_tour(m)
    _goto_card(m, C_GI)
    m.press("UP")                          # On -> Off
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_MUSIC, NO_GI))       # menu music takes the video's place
    assert m.has(otr(f"onb_f{C_MUSIC}_name")), m.text()
    m.close()
    sd = t.sd(config=FRESH + "ShowGameInfo: 2\nGameInfoVideo: true\nGameInfoMusic: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_VIDEO)
    assert m.has(otr(f"onb_f{C_VIDEO}_name")), m.text()
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_MUSIC, NO_VIDEO))    # the clip's music is left out
    assert m.has(otr(f"onb_f{C_MUSIC}_name")), m.text()
    _finish(m)
    m.close()
    cfg = _cfg(t, sd)
    assert "GameInfoVideo: false" in cfg and "GameInfoMusic: true" in cfg, cfg


def test_tour_clip_music_card_saves(t):
    """With the card and its clip on, the music card asks and keeps its No."""
    sd = t.sd(config=FRESH + "ShowGameInfo: 1\nGameInfoVideo: true\nGameInfoMusic: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_CLIPMUSIC)
    assert m.has(otr(f"onb_f{C_CLIPMUSIC}_name")), m.text()
    m.press("DOWN")
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_MUSIC))
    _finish(m)
    m.close()
    assert "GameInfoMusic: false" in _cfg(t, sd), _cfg(t, sd)


def test_tour_sd2snes_folder_card_saves(t):
    sd = t.sd(config=FRESH + "ShowSd2snesFolder: false\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_SD2SNESDIR)
    assert m.has(otr(f"onb_f{C_SD2SNESDIR}_name")), m.text()
    lit = _list_lit(m, otr("onb_text_yes"))
    m.wait(lambda: lit(1) > lit(0) + 40, what="a barra em Nao (o valor salvo)")
    m.press("UP")                          # -> Yes
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_RESET))
    _finish(m)
    m.close()
    assert "ShowSd2snesFolder: true" in _cfg(t, sd), _cfg(t, sd)


def test_tour_competition_cart_round_scrolls(t):
    """Sixteen answers (3..18 min) do not fit under the text: the list scrolls with the bar
    and the menu's scroll bar shows. The bar starts on the saved 6 min; the last one is kept."""
    sd = t.sd(config=FRESH + "CompCartTimeLimit: 3\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_CCTIME)
    import re
    first, last = otr("onb_text_cc_3"), otr("onb_text_cc_18")
    shows_3 = lambda: re.search(r"(?<!\d)" + re.escape(first), m.text()) is not None  # not "13 min"
    assert shows_3() and not m.has(last), m.text()
    lit = _list_lit(m, first)
    m.wait(lambda: lit(3) > lit(0) + 40, what="a barra em 6 min")
    thumb = lambda: [r for r in range(28) if m.tile_at(29, r)[0] == 17]   # ONB_SB_X, glyph 17
    assert thumb(), m.text()               # the menu's scroll bar: its thumb...
    top = thumb()[0]
    for _ in range(14):
        m.press("DOWN")
        m.step(12)
    m.wait_text(last)                      # scrolled down to it...
    assert not shows_3(), m.text()         # ...and the first one went off the top
    assert thumb() and thumb()[0] > top, (top, thumb())   # ...and the thumb went down
    m.press("A")
    m.wait_text(hdr(C_CONSOLES))
    _finish(m)
    m.close()
    assert "CompCartTimeLimit: 15" in _cfg(t, sd), _cfg(t, sd)


def test_tour_new_info_cards_show_their_text(t):
    """The info-only cards of the base tour draw their name and first line (the Mk.II's
    LED card is not shown on the Ciclone's Mk.III)."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    for n in (C_THEME, C_PCM, C_CHEATLIST, C_SAVES, C_TRAINER, C_PATCHES, C_CREATEROM, C_CHIPS,
              C_SUFAMI, C_CONSOLES, C_ATARI, C_FOLDERS, C_MEMTEST):
        _goto_card(m, n)
        assert m.has(otr(f"onb_f{n}_name")), (n, m.text())
        m.wait_text(para(n))
    m.close()


def test_tour_card_order(t):
    """The tour's order, by its English names: the look, the music, the file list, the
    cheats and the in-game menu, the patches and the chips, the other consoles, the card and
    the hardware, "And more", then the 2.17 section. The NES/SMS/Atari buttons card is gone
    (its reset and menu combos are the usual ones; the NES palette one is on the consoles
    card), and the special chips item of "And more" became a card."""
    name = lambda n: onb.NAMES[n - 1][0]
    assert len(onb.NAMES) == NCARDS + MORE_ITEMS
    assert [name(n) for n in range(1, NCARDS + 1)] == [
        "Language", "Themes", "Text outline", "Text anti-aliasing", "Box art in the list",
        "Covers in Recent/Favorites", "Game info card", "Video in the game info",
        "Music of the video", "Menu music", "Random music", "Menu sounds", "MSU-1 folders",
        "MSU-1 track player", "Show sd2snes folder", "Smart reset", "The cheat list",
        "In-game menu", "Savestates", "4 saves per game", "RAM trainer", "IPS/BPS patches",
        "Create patched ROM", "More special chips", "Sufami Turbo Slot B",
        "Competition Cart round", "Other consoles", "Atari 2600 controls",
        "Folders on the card", "Memory test", "Mk.II boot errors on the LED", "And more",
        "What's new in 2.17", "Controller 2 shortcuts/hooks", "Game Boy Color",
        "Shortcut/hook list", "Seta chips and bootlegs", "Super 20 in 1, Gamars, .sfrom",
        "Icons in the list", "Cheats from the game info"]
    items = [name(n) for n in range(NCARDS + 1, NCARDS + MORE_ITEMS + 1)]
    assert items == ["Clear PPU on boot", "Bus timing compat", "Hardware model",
                     "BS-X and Memory Pack", "Delete files and saves", "Missing BIOS warning",
                     "Clock and date", "Option descriptions"], items


def _descriptors():
    """onb_feat_table as written: (n, parent, second parent, flags, option kind)."""
    import re
    src = (c.SD2SNES / "snes" / "onboarding" / "onboarding_const.a65").read_text()
    rows = re.findall(r"^\s*\.word ([^,]+), 1, onb_f(\d+)_name, onb_f\d+_text, ([^,]+), ([^ ;]+)"
                      r"[^\n]*\n\s*\.byt ONB_PAL_\w+, ONB_OPT_(\w+)", src, re.M)
    return [(int(n), dep.strip(), dep2.strip(), fl.strip(), opt) for dep, n, dep2, fl, opt in rows]


def test_tour_descriptors_per_board(t):
    """The cards of the cores only the FXPAK PRO (Mk.III) has (other consoles, the Atari's
    controls, Game Boy Color) are flagged for it, the Mk.II's LED codes for the Mk.II: 39
    cards on a Mk.III, 37 on a Mk.II. The dependencies point at the right parents after the
    reorder, and the hook flags sit on the in-game menu, savestates and controller 2 cards."""
    d = {n: (dep, dep2, fl, opt) for n, dep, dep2, fl, opt in _descriptors()}
    assert sorted(d) == list(range(1, NCARDS + MORE_ITEMS + 1)), sorted(d)
    mk3 = [n for n in d if "ONB_FF_MK3ONLY" in d[n][2]]
    mk2 = [n for n in d if "ONB_FF_MK2ONLY" in d[n][2]]
    assert mk3 == list(MK3ONLY) and mk2 == list(MK2ONLY), (mk3, mk2)
    cards = range(1, NCARDS + 1)
    assert len([n for n in cards if n not in mk2]) == 39
    assert len([n for n in cards if n not in mk3]) == 37
    hook = {n for n in d if "ONB_FF_HOOK" in d[n][2]}
    assert hook == {C_IGM, C_STATES, C_PAD2}, hook
    assert "ONB_FF_BUTTONS" in d[C_PAD2][2]
    parents = {n: (d[n][0], d[n][1]) for n in d if d[n][0] != "0" or d[n][1] != "0"}
    assert parents == {
        C_COVLISTS: ("!CFG_SHOW_COVERS", "0"),
        C_VIDEO: ("!CFG_SHOW_GAME_INFO", "0"),
        C_CLIPMUSIC: ("!CFG_GAME_INFO_VIDEO", "!CFG_SHOW_GAME_INFO"),
        C_RANDOM: ("!CFG_ENABLE_MENU_MUSIC", "0"),
        C_SAVES: ("!CFG_ENABLE_CHEAT_OVERLAY", "0"),
        C_TRAINER: ("!CFG_ENABLE_CHEAT_OVERLAY", "0"),
    }, parents
    assert d[MORE_CARD][3] == "MORE"


def test_tour_ingame_menu_cards_depend_on_it(t):
    """The 4 saves and the RAM trainer live in the in-game menu: its No leaves both out (Right
    from savestates lands on the patches card); with it on, each follows its card."""
    m = t.menu(t.sd(config=FRESH + "EnableCheatOverlay: true\n"))
    _enter_tour(m)
    _goto_card(m, C_IGM)
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_STATES, NO_IGM))
    m.step(30)
    m.press("A")
    m.wait_text(hdr(C_PATCHES, NO_IGM))
    assert m.has(otr(f"onb_f{C_PATCHES}_name")), m.text()      # the 4 saves and the trainer left out
    m.step(30)
    m.press("LEFT")                        # back skips them too
    m.wait_text(hdr(C_STATES, NO_IGM))
    assert m.has(otr(f"onb_f{C_STATES}_name")), m.text()
    m.step(30)
    m.press("LEFT")
    m.wait_text(hdr(C_IGM, NO_IGM))
    m.step(30)
    m.press("UP")                          # the kept No -> Yes
    m.step(10)
    m.press("A")                           # both come back
    m.wait_text(hdr(C_STATES))
    m.step(30)
    m.press("A")
    m.wait_text(hdr(C_SAVES))
    assert m.has(otr(f"onb_f{C_SAVES}_name")), m.text()
    m.wait_text(para(C_SAVES))
    m.step(30)
    m.press("RIGHT")
    m.wait_text(hdr(C_TRAINER))
    assert m.has(otr(f"onb_f{C_TRAINER}_name")), m.text()
    m.wait_text(para(C_TRAINER))
    m.close()


# the CFG bytes the hook-dependent cards touch (offsets in cfg_t, bank $FF from $FF0100)
CFG_HOOK, CFG_BUTTONS, CFG_STATES, CFG_OVERLAY, CFG_PAD2 = 0x11, 0x12, 0xA3, 0x13D, 0x1D3
HOOK_OFF = FRESH + "EnableIngameHook: false\nEnableIngameButtons: false\n"


def _cfgb(m, off):
    """A byte of the CFG block as the tour leaves it (the MCU saves it at the end)."""
    return m.psram(0xFF0100 + off, 1)[0]


def _walk_to(m, pos, total):
    """Right until the header says pos/total (Right keeps each card's focused answer)."""
    for _ in range(total + 2):
        if m.has(f"{pos}/{total}"):
            m.step(30)
            return
        m.press("RIGHT")
        m.step(40)
    raise c.MenuError(f"card {pos}/{total} not reached\n{m.text()}")


def test_tour_hook_cards_shown_with_the_hook_off(t):
    """The cards of the in-game hook features do not hang on the hook: with it off, the
    tour still counts all of them (the 4 saves and the trainer only follow the in-game
    menu card)."""
    m = t.menu(t.sd(config=HOOK_OFF + "EnableCheatOverlay: true\n"))
    _enter_tour(m, total=TOTAL)
    assert _cfgb(m, CFG_HOOK) == 0
    _walk_to(m, pos(C_CHEATLIST), TOTAL)
    assert _cfgb(m, CFG_HOOK) == 0
    m.close()


def test_tour_ingame_menu_yes_turns_the_hook_on(t):
    """Yes on the in-game menu card with the hook off keeps the menu AND turns the hook on
    (the in-game buttons are not needed by it and stay as they were); the 4 saves and the
    trainer come in with it."""
    total = tot(NO_IGM)                    # the menu off: the 4 saves and the trainer left out
    sd = t.sd(config=HOOK_OFF + "EnableCheatOverlay: false\n")
    m = t.menu(sd)
    _enter_tour(m, total=total)
    _walk_to(m, pos(C_IGM, NO_IGM), total)
    assert m.has(otr(f"onb_f{C_IGM}_name")), m.text()
    assert _cfgb(m, CFG_HOOK) == 0
    m.press("UP")                          # No -> Yes
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_STATES))
    assert (_cfgb(m, CFG_OVERLAY), _cfgb(m, CFG_HOOK), _cfgb(m, CFG_BUTTONS)) == (1, 1, 0)
    m.step(30)
    m.press("RIGHT")
    m.wait_text(hdr(C_SAVES))
    assert m.has(otr(f"onb_f{C_SAVES}_name")), m.text()
    _finish(m)
    m.close()
    cfg = _cfg(t, sd)
    for want in ("EnableCheatOverlay: true", "EnableIngameHook: true", "EnableIngameButtons: false"):
        assert want in cfg, (want, cfg)


def test_tour_no_never_turns_the_hook_off(t):
    """No on the in-game menu and on the savestates cards keeps the hook on; the in-game
    menu off still leaves the 4 saves and the trainer out (Right from savestates lands on
    the patches card, Left goes back to savestates)."""
    sd = t.sd(config=FRESH + "EnableCheatOverlay: true\nEnableIngameSavestate: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, C_IGM)
    assert _cfgb(m, CFG_HOOK) == 1
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_STATES, NO_IGM))
    assert (_cfgb(m, CFG_OVERLAY), _cfgb(m, CFG_HOOK)) == (0, 1)
    m.step(30)
    m.press("DOWN")                        # savestates: Yes -> No
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_PATCHES, NO_IGM))
    assert m.has(otr(f"onb_f{C_PATCHES}_name")), m.text()      # the 4 saves and the trainer left out
    assert (_cfgb(m, CFG_STATES), _cfgb(m, CFG_HOOK)) == (0, 1)
    m.step(30)
    m.press("RIGHT")
    m.wait_text(hdr(C_CREATEROM, NO_IGM))
    m.step(30)
    m.press("LEFT")
    m.wait_text(hdr(C_PATCHES, NO_IGM))
    m.step(30)
    m.press("LEFT")
    m.wait_text(hdr(C_STATES, NO_IGM))
    _finish(m)
    m.close()
    cfg = _cfg(t, sd)
    for want in ("EnableCheatOverlay: false", "EnableIngameSavestate: 0", "EnableIngameHook: true"):
        assert want in cfg, (want, cfg)


def test_tour_savestates_yes_turns_the_hook_on(t):
    """Yes on the savestates card turns the hook on too; a No kept on the in-game menu
    card before it left the hook off."""
    total = tot(NO_IGM)
    m = t.menu(t.sd(config=HOOK_OFF + "EnableCheatOverlay: false\nEnableIngameSavestate: false\n"))
    _enter_tour(m, total=total)
    _walk_to(m, pos(C_STATES, NO_IGM), total)   # Right on the in-game menu card kept its No
    assert m.has(otr(f"onb_f{C_STATES}_name")), m.text()
    assert (_cfgb(m, CFG_OVERLAY), _cfgb(m, CFG_HOOK)) == (0, 0)
    m.press("UP")                          # No -> Yes
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_PATCHES, NO_IGM))
    assert (_cfgb(m, CFG_STATES), _cfgb(m, CFG_HOOK), _cfgb(m, CFG_BUTTONS)) == (1, 1, 0)
    m.close()


def test_tour_pad2_yes_turns_the_hook_and_buttons_on(t):
    """The controller 2 card needs the hook and the in-game buttons (the FPGA's fixed
    gestures): its Yes turns both on, after the Nos kept on the cards before left them off."""
    total = tot(NO_IGM)
    sd = t.sd(config=HOOK_OFF + "EnableCheatOverlay: false\nEnableIngameSavestate: false\n")
    m = t.menu(sd)
    _enter_tour(m, total=total)
    _walk_to(m, pos(C_PAD2, NO_IGM), total)   # the 4 saves and the trainer are left out before it
    assert m.has(otr(f"onb_f{C_PAD2}_name")), m.text()
    assert (_cfgb(m, CFG_HOOK), _cfgb(m, CFG_BUTTONS), _cfgb(m, CFG_PAD2)) == (0, 0, 0)
    m.press("UP")                          # No -> Yes
    m.step(10)
    m.press("A")
    m.wait_text(hdr(C_GBC, NO_IGM))
    assert (_cfgb(m, CFG_HOOK), _cfgb(m, CFG_BUTTONS), _cfgb(m, CFG_PAD2)) == (1, 1, 1)
    _finish(m)
    m.close()
    cfg = _cfg(t, sd)
    for want in ("EnableIngamePad2: true", "EnableIngameHook: true", "EnableIngameButtons: true"):
        assert want in cfg, (want, cfg)
