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


NCARDS = 21
MORE_CARD = 12      # "and more": the base tour's last card, 12 items (a list that scrolls)
SECTION_CARD = 13   # the 2.17 section's opening card, then the release's cards (14..21)

sys.path.insert(0, str(c.SD2SNES / "snes" / "utils"))
import gen_onb_lang as onb  # noqa: E402  the tour's own strings (not in the menu dicts)
sys.path.pop(0)


def otr(label, lang="en"):
    """A tour string as the screen decodes it."""
    return c.encode_menu_text(onb.STRINGS[label][onb.LANGS.index(lang)])


def para(n, lang="en", line=0):
    """A line of card n's paragraph (gen_onb_lang.py wraps it) as the screen decodes it."""
    return c.encode_menu_text(onb.STRINGS["onb_f%d_text" % n][onb.LANGS.index(lang)][line])


def _enter_tour(m, lang="en"):
    """Answer yes to the first-boot question and wait for the tour's first card."""
    m.wait_text(c.encode_menu_text(c.tr("text_onbg_question", lang)))
    m.press("A")
    m.wait(lambda: "/sd2snes/onboarding.bin" in m.fwlog(), frames=900, what="a carga do tour")
    # the first card; "/12" when a card is left out (random music without music)
    m.wait(lambda: m.has(f"1/{NCARDS}") or m.has(f"1/{NCARDS - 1}"), frames=1500,
           what="o primeiro card do tour")
    m.step(30)                             # the card fades in; a press during the ramp is lost


def _goto_card(m, n):
    """From a card before n (Right), until the header says n/NCARDS."""
    for _ in range(NCARDS + 2):
        if m.has(f"{n}/{NCARDS}"):
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
    assert not m.has(f"1/{NCARDS}"), m.text()
    m.close()
    assert SEEN in _cfg(t, sd)


def test_tour_answers_are_saved(t):
    """A list per card, the menu's bar on the focused answer: Up/Down move it (and stop
    at the ends), A keeps the focused answer and goes on to the next card. Going back
    with Left keeps the old value. The "all set" screen's A saves config.yml."""
    sd = t.sd(config=FRESH + "ShowCovers: 1\nEnableMenuMusic: true\nMenuMusicRandom: true\n")
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, 2)                       # box art: Off / Large / Small, bar on Large
    m.press("DOWN")                        # -> Small
    m.step(10)
    m.press("DOWN")                        # the last one: stays
    m.step(10)
    m.press("A")                           # keep Small, next card
    m.wait_text(f"3/{NCARDS}")
    _goto_card(m, 4)                       # menu music: Yes / No, bar on Yes
    m.press("DOWN")
    m.step(10)
    m.press("A")                           # keep No: random music (card 5) is left out
    m.wait_text(f"5/{NCARDS - 1}")         # the menu sounds card, now 5 of 12
    assert m.has(otr("onb_f6_name")), m.text()
    m.step(30)
    m.press("LEFT")                        # back skips it too
    m.wait_text(f"4/{NCARDS - 1}")
    assert m.has(otr("onb_f4_name")), m.text()
    m.step(30)
    m.press("RIGHT")
    m.wait_text(f"5/{NCARDS - 1}")
    m.step(30)
    m.press("DOWN")                        # menu sounds: moved but not kept...
    m.step(10)
    m.press("LEFT")                        # ...going back leaves it as it was
    m.wait_text(f"4/{NCARDS - 1}")
    m.step(30)
    m.press("RIGHT")                       # the bar sits on the kept answers again
    m.wait_text(f"5/{NCARDS - 1}")
    m.step(30)
    for _ in range(NCARDS):                # Right past the last card
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


def test_tour_guides_card_follows_the_ingame_menu(t):
    """Guides live inside the in-game menu: with the in-game menu card answered No the
    guides card is left out, going forward and coming back."""
    m = t.menu(t.sd(config=FRESH + "EnableMenuMusic: true\nEnableCheatOverlay: true\n"))
    _enter_tour(m)
    _goto_card(m, 7)                       # in-game menu: Yes / No, bar on Yes
    assert m.has(otr("onb_f7_name")), m.text()
    m.press("DOWN")
    m.step(10)
    m.press("A")                           # No -> savestates, 8 of 12
    m.wait_text(f"8/{NCARDS - 1}")
    assert m.has(otr("onb_f8_name")), m.text()
    m.step(30)
    m.press("RIGHT")                       # guides (card 9) is left out
    m.wait_text(f"9/{NCARDS - 1}")
    assert m.has(otr("onb_f10_name")), m.text()
    assert not m.has(otr("onb_f9_name")), m.text()
    m.step(30)
    m.press("LEFT")                        # and back skips it too
    m.wait_text(f"8/{NCARDS - 1}")
    assert m.has(otr("onb_f8_name")), m.text()


def test_tour_demo_follows_the_focus(t):
    """The demo picture streams into the hidden VRAM slot and the 16 sprites swap to
    it: moving the bar on the box-art card flips them from slot 0 (name table 0, OBJ
    palettes 0-3) to slot 1 (table 1, palettes 4-7), and back."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, 2)
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
    each one's text beside the list (and its demo). Twelve items do not fit: the list
    scrolls with the bar down to the last one. A goes on to the 2.17 section."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, MORE_CARD)
    assert m.has(otr(f"onb_f{MORE_CARD}_name")), m.text()          # "And more"
    first = NCARDS + 1                                              # its items: after the cards
    assert m.has(para(first)), m.text()                            # item 1's text (themes)
    assert m.has(otr(f"onb_f{first}_name")), m.text()
    last = first + 11
    assert not m.has(otr(f"onb_f{last}_name")), m.text()           # below the box, for now
    m.press("DOWN")
    m.wait_text(para(first + 1))                                   # item 2 (cheats) beside the list
    for _ in range(12):
        m.press("DOWN")
        m.step(12)
    m.wait_text(para(last))                                        # the last item's text...
    assert m.has(otr(f"onb_f{last}_name")), m.text()               # ...and the list scrolled to it
    assert not m.has(otr(f"onb_f{first}_name")), m.text()
    m.press("A")
    m.wait_text(f"{SECTION_CARD}/{NCARDS}")


def test_tour_217_section(t):
    """After the base tour, a card opens the 2.17 section, then the release's cards:
    controller 2, Game Boy Color, the in-game shortcut list, the community cartridges,
    the browser icons, cheats from the game info card, the experimental-core warning; then
    "all set"."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    _goto_card(m, SECTION_CARD)
    assert m.has(otr(f"onb_f{SECTION_CARD}_name")), m.text()      # "What's new in 2.17"
    assert m.has(para(SECTION_CARD)), m.text()
    for n in range(SECTION_CARD + 1, NCARDS + 1):
        m.press("RIGHT")
        m.wait_text(f"{n}/{NCARDS}")
        assert m.has(otr(f"onb_f{n}_name")), (n, m.text())
        m.step(30)
    m.press("RIGHT")
    m.wait_text(otr("onb_ui_done_title"))


def test_tour_experimental_warning_card(t):
    """The experimental-core warning card is a Yes/No answer: "No" and A turn the
    question off (WarnExperimental: false in config.yml)."""
    sd = t.sd(config=FRESH)
    m = t.menu(sd)
    _enter_tour(m)
    _goto_card(m, NCARDS)
    assert m.has(otr(f"onb_f{NCARDS}_name")), m.text()
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("A")
    m.wait_text(otr("onb_ui_done_title"))
    m.step(30)
    m.press("A")
    _back_to_menu(m)
    m.close()
    assert "WarnExperimental: false" in _cfg(t, sd), _cfg(t, sd)


def test_tour_217_credits(t):
    """The two community cartridge cards name who made the cores, in every language's
    paragraph and on the screen."""
    for n, who in ((17, "M2M"), (18, "terminator2k2")):
        for k in range(len(onb.LANGS)):
            assert any(who in line for line in onb.STRINGS["onb_f%d_text" % n][k]), (n, k)
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    for n, who in ((17, "M2M"), (18, "terminator2k2")):
        _goto_card(m, n)
        line = next(i for i, l in enumerate(onb.STRINGS["onb_f%d_text" % n][0]) if who in l)
        m.wait_text(para(n, line=line))
        m.step(30)


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
    _goto_card(m, 4)
    m.press("DOWN")                                   # No: the music stops
    m.wait(lambda: "RESET requested by SNES" in tour_log(), frames=600, what="o reset")
    m.wait_text(f"4/{NCARDS}", frames=1500)            # back on the same card
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
    _goto_card(m, 6)
    assert m.has(otr("onb_f6_name")), m.text()
    assert _sfx_count(m, n) == 0, m.fwlog()[n:]
    m.press("UP")                              # Yes: the preview
    m.wait(lambda: _sfx_count(m, n) > 0, what="a previa do som")
    m.step(40)
    m.press("LEFT")                            # left without answering
    m.wait_text(f"5/{NCARDS}")
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
    _goto_card(m, 4)
    m.press("DOWN")
    m.wait(lambda: "RESET requested by SNES" in tour_log(), frames=600, what="o reset")
    m.wait_text(f"4/{NCARDS}", frames=1500)
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
    _goto_card(m, 4)
    m.press("DOWN")                        # Yes -> No
    m.step(10)
    m.press("RIGHT")
    m.wait_text(f"5/{NCARDS - 1}")         # the menu sounds card, random music left out
    assert m.has(otr("onb_f6_name")), m.text()
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
    m.wait_text(f"2/{NCARDS}")


def test_tour_opens_on_the_first_card_and_back_stays(t):
    """No opening screen: the tour starts on its first card, and B there does nothing."""
    m = t.menu(t.sd(config=FRESH))
    _enter_tour(m)
    assert m.has(otr("onb_f1_name")), m.text()
    m.press("B")
    m.step(60)
    assert m.has(f"1/{NCARDS}"), m.text()


def _tour_in(t, idx):
    """Every card of the tour, and the "all set" screen, draw in language idx with no
    unknown glyph (a character outside the font's ACCENTS/HOMOGLYPHS turns into garbage
    silently)."""
    lang = c.LANGS[idx]
    m = t.menu(t.sd(config=f"---\nLanguage: {idx}\nOnboardingVersion: 0\n"))
    _enter_tour(m, lang)
    for n in range(1, NCARDS + 1):
        _goto_card(m, n)
        assert c.UNKNOWN not in m.text(), f"{lang}: card {n}\n{m.text()}"
    m.press("RIGHT")
    m.wait(lambda: not m.has(f"{NCARDS}/{NCARDS}"), what="a tela final")
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
    m.wait_text(f"1/{NCARDS}", frames=1500)        # the whole tour, from its first card
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
    m.wait(lambda: m.has(f"1/{NCARDS}") or m.has(f"1/{NCARDS - 1}"), frames=900, what="o primeiro card")
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
    m.wait(lambda: m.has(f"1/{NCARDS}") or m.has(f"1/{NCARDS - 1}"), frames=900, what="o primeiro card")
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
    m.wait(lambda: m.has(f"1/{NCARDS}") or m.has(f"1/{NCARDS - 1}"), frames=1500, what="o primeiro card")
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
    m.wait(lambda: m.has(f"1/{NCARDS}") or m.has(f"1/{NCARDS - 1}"), frames=1500, what="o primeiro card")
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
    m.wait(lambda: m.has(f"1/{NCARDS}"), frames=900, what="o primeiro card")
    m.step(30)
    for _ in range(6):                             # page to card 2 (box art); like _goto_card,
        if m.has(f"2/{NCARDS}"):                   # a press right after the fade can be lost
            break
        m.press("RIGHT", pad=2)
        m.step(40)
    assert m.has(f"2/{NCARDS}"), m.text()
    m.step(30)
    m.press("DOWN", pad=2)                         # Large -> Small
    m.step(10)
    m.press("A", pad=2)                            # keep it
    m.wait_text(f"3/{NCARDS}")
    m.step(30)
    m.press("START", pad=2)                        # end the tour
    _back_to_menu(m)
    m.close()
    cfg = _cfg(t, sd)
    assert "ShowCovers: 2" in cfg and SEEN in cfg, cfg
