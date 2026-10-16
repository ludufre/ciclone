"""A tela de Saves: o "Saves..." do menu de contexto (lista, Recentes, Favoritos) e o R da ficha
abrem os saves e os savestates do jogo, um slot por linha, com a data na ordem do idioma e o
tamanho; o slot com que o jogo inicia sai em verde (paleta 2). A num slot: usar ao iniciar (grava o .slot),
duplicar para outro slot do mesmo tipo, apagar."""
import re
import time

import ciclone as c

T0 = time.mktime((2026, 10, 15, 13, 42, 0, 0, 0, -1))
SAVES = "/sd2snes/saves/TE"
STATES = "/sd2snes/states/TE"
SRM1 = f"{SAVES}/Test Game.srm"
SRM2 = f"{SAVES}/Test Game.02.srm"
SRM3 = f"{SAVES}/Test Game.03.srm"
ST1 = f"{STATES}/Test Game01.state"
SLOT = f"{SAVES}/Test Game.slot"
SS_SLOTS = 0xFE100F                                # the savestate handler's current slot


def _card(t, files, config=None, extra=None):
    x = {p: (d, T0) for p, d in files.items()}
    x.update(extra or {})
    return t.sd(config=config, extra=x)


GREEN, GREY = 2, 6


def _slot_re(n, lang="en"):
    return re.compile(r"(^| )" + re.escape(c.tr("text_saves_slot", lang)) + " " + str(n) + r"( |$)")


def _slot_row(m, kind, n, lang="en"):
    """Screen row of slot n of a kind: the slot rows sit under the kind's header (its name
    and the Date column, in blue), and a row no longer repeats the kind."""
    rows = m.screen()
    head, date = c.tr(kind, lang), c.tr("text_saves_date", lang)
    h = next((i for i, r in enumerate(rows) if head in r and date in r), None)
    if h is None:
        raise c.MenuError(f"sem o cabeçalho {kind}\n{m.text()}")
    pat = _slot_re(n, lang)
    for i in range(h + 1, min(h + 5, len(rows))):
        if pat.search(rows[i]):
            return i
    raise c.MenuError(f"sem a linha {kind} {n}\n{m.text()}")


def _line(m, kind, n, lang="en"):
    return m.screen()[_slot_row(m, kind, n, lang)]


def _pal(m, kind, n):
    """Palette of the slot's row (the cell of its slot word)."""
    y = _slot_row(m, kind, n)
    x = m.screen()[y].index(c.tr("text_saves_slot"))
    return m.tile_at(x, y)[1]


def _starts(m, kind, n):
    return _pal(m, kind, n) == GREEN


def _bar_to(m, test, what, tries=12):
    for _ in range(tries):
        if test(m.bar_row()):
            return
        m.press("DOWN")
        m.step(8)
    raise c.MenuError(f"{what} não está na lista\n{m.text()}")


def _bar_to_label(m, label):
    want = c.tr(label)
    _bar_to(m, lambda r: want in r, label)


def _bar_to_slot(m, kind, n):
    for _ in range(12):
        row = _slot_row(m, kind, n)
        bar = m.u8("bar_yl") + 1
        if bar == row:
            return
        m.press("DOWN" if bar < row else "UP")
        m.step(8)
    raise c.MenuError(f"a barra não chega em {kind} {n}\n{m.text()}")


def _wait_rows(m, lang="en"):
    m.wait(lambda: m.has(c.tr("text_saves_date", lang)) and any(
        _slot_re(1, lang).search(r) for r in m.screen()), what="a tela de Saves")
    m.settle()


def _open_from_browser(m):
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    _bar_to_label(m, "text_filesel_context_saves")
    m.press("A")
    _wait_rows(m)


def _confirm_yes(m):
    m.wait_text(c.tr("text_confirm_hint"))
    m.settle()
    yes = c.tr("text_confirm_yes_sel")
    for _ in range(4):
        if m.has(yes):
            break
        m.press("LEFT")
        m.step(8)
    assert m.has(yes), m.text()
    m.press("A")
    m.settle()


def _action(m, kind, n, label):
    """A on the slot, then the action row `label`."""
    _bar_to_slot(m, kind, n)
    m.press("A")
    m.settle()
    _bar_to_label(m, label)
    m.press("A")
    m.settle()


def test_each_slot_with_its_date_and_size(t):
    sd = _card(t, {SRM1: b"\x5a" * 2048, ST1: b"\x33" * 4096})
    m = t.menu(sd)
    _open_from_browser(m)
    s1 = _line(m, "text_saves_srm", 1)
    assert _starts(m, "text_saves_srm", 1), s1       # the slot the game starts with
    assert "10/15/2026 13:42" in s1 and "2 KB" in s1, s1
    assert c.tr("text_saves_empty") in _line(m, "text_saves_srm", 2)
    st = _line(m, "text_saves_state", 1)
    assert "10/15/2026 13:42" in st and "4 KB" in st, st
    assert c.tr("text_saves_empty") in _line(m, "text_saves_state", 4)
    assert m.has(c.tr("text_saves_size")) and m.has(c.tr("text_saves_keys")), m.text()
    assert "*" not in _line(m, "text_saves_srm", 1)
    m.press("B")
    m.wait(lambda: not m.has(c.tr("text_saves_date")), what="a lista fechada")
    m.close()


def test_the_date_follows_the_menu_language(t):
    """Português: dia/mês/ano, como o relógio."""
    sd = _card(t, {SRM1: b"\x5a" * 2048}, config="---\nLanguage: 1\n")
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    want = c.tr("text_filesel_context_saves", "ptbr").split("{")[0]
    _bar_to(m, lambda r: want in r, "Saves")
    m.press("A")
    _wait_rows(m, "ptbr")
    assert "15/10/2026 13:42" in _line(m, "text_saves_srm", 1, lang="ptbr"), m.text()
    m.close()


def test_delete_one_slot(t):
    sd = _card(t, {SRM1: b"\x5a" * 2048, SRM2: b"\x6b" * 2048})
    m = t.menu(sd)
    _open_from_browser(m)
    _action(m, "text_saves_srm", 2, "text_filesel_context_delete_file")
    m.wait_text(c.tr("text_confirm_hint"))
    assert m.has(c.tr("text_saves_slot") + " 2 - 10/15/2026 13:42"), m.text()   # not the padded row
    _confirm_yes(m)
    m.wait(lambda: c.tr("text_saves_empty") in _line(m, "text_saves_srm", 2), what="o slot 2 vazio")
    assert "13:42" not in _line(m, "text_saves_srm", 2), _line(m, "text_saves_srm", 2)   # no leftover of the old text
    assert "13:42" in _line(m, "text_saves_srm", 1)
    m.close()
    names = t.listdir(sd, SAVES)
    assert "Test Game.02.srm" not in names and "Test Game.srm" in names, names


def test_duplicate_onto_an_empty_slot(t):
    sd = _card(t, {SRM1: b"\x11" * 2048})
    m = t.menu(sd)
    _open_from_browser(m)
    _action(m, "text_saves_srm", 1, "text_saves_copy")
    _bar_to(m, lambda r: _slot_re(3).search(r) is not None, "o destino 3")   # the other slots
    m.press("A")
    m.wait(lambda: c.tr("text_saves_empty") not in _line(m, "text_saves_srm", 3), what="o slot 3")
    m.close()
    assert t.read(sd, SRM3) == b"\x11" * 2048


def test_duplicate_over_a_save_asks_first(t):
    sd = _card(t, {SRM1: b"\x11" * 2048, SRM2: b"\x22" * 2048})
    m = t.menu(sd)
    _open_from_browser(m)
    _action(m, "text_saves_srm", 1, "text_saves_copy")
    _bar_to(m, lambda r: _slot_re(2).search(r) is not None, "o destino 2")
    m.press("A")
    m.wait_text(c.tr("text_saves_overwrite"))
    _confirm_yes(m)
    m.close()
    assert t.read(sd, SRM2) == b"\x11" * 2048


def test_use_when_starting_writes_the_slot_sidecar(t):
    """Byte 0 = o slot do save de bateria, byte 1 = o do savestate ('1'..'4')."""
    sd = _card(t, {SRM1: b"\x5a" * 2048})
    m = t.menu(sd)
    _open_from_browser(m)
    _action(m, "text_saves_srm", 2, "text_saves_use")
    m.wait(lambda: _starts(m, "text_saves_srm", 2), what="o '*' no slot 2")
    assert not _starts(m, "text_saves_srm", 1)
    _action(m, "text_saves_state", 3, "text_saves_use")
    m.wait(lambda: _starts(m, "text_saves_state", 3), what="o '*' no estado 3")
    m.close()
    assert t.read(sd, SLOT) == b"23"


def test_the_game_starts_on_the_chosen_savestate_slot(t):
    sd = _card(t, {}, extra={SLOT: b"13"})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot")
    assert m.psram(SS_SLOTS, 1)[0] & 0x7f == 3, m.psram(SS_SLOTS, 1)
    m.close()


def test_r_on_the_info_screen(t):
    sd = _card(t, {SRM1: b"\x5a" * 2048})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("R")
    _wait_rows(m)
    assert "13:42" in _line(m, "text_saves_srm", 1), m.text()
    m.press("B")
    m.step(4)                                        # the bar goes with the list: it showed over
    assert (m.u8("bar_xl"), m.u8("bar_wl")) == (0xFF, 0xFF)   # the info screen while it came back
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de volta")
    m.close()


def test_from_recents(t):
    sd = _card(t, {SRM1: b"\x5a" * 2048}, extra={"/sd2snes/lastgame.cfg": b"/Test Game.sfc\0"})
    m = t.menu(sd)
    m.press("START")
    m.wait_text(c.tr("text_last"))
    m.press("Y")
    m.settle()
    _bar_to_label(m, "text_filesel_context_saves")
    m.press("A")
    _wait_rows(m)
    assert "13:42" in _line(m, "text_saves_srm", 1), m.text()
    m.close()


def test_the_bar_skips_the_headers_and_blank_lines(t):
    """Down from the 4th battery save lands on the 1st savestate: the blank line and the
    savestates' header in between are not rows; Up from there comes back."""
    sd = _card(t, {SRM1: b"\x5a" * 2048})
    m = t.menu(sd)
    _open_from_browser(m)
    _bar_to_slot(m, "text_saves_srm", 4)
    m.press("DOWN")
    m.step(8)
    assert m.u8("bar_yl") + 1 == _slot_row(m, "text_saves_state", 1), m.text()
    m.press("UP")
    m.step(8)
    assert m.u8("bar_yl") + 1 == _slot_row(m, "text_saves_srm", 4), m.text()
    m.close()


def _cov() -> bytes:
    """.cov v4 sintético (o mesmo do test_gameinfo_assets): 2x2 sprites de 16x16."""
    w = h = 2
    hdr = bytes([ord("C"), ord("V"), 4, 0, w, h, 1, 0, 4, 0, 0, 0])
    pal = b"\x00\x00" + b"".join(((i * 0x0842) & 0x7FFF).to_bytes(2, "little") for i in range(1, 16))
    tiles = bytes([0xAA, 0x55] * 8 + [0xFF, 0x0F] * 8) * ((2 * h) * 16)
    return hdr + pal + bytes(w * h) + tiles


def test_the_cover_hides_while_open_and_comes_back(t):
    """A cover still loading when the context menu opens lands under it (a slow card, the
    MCU not held): the screen hides it, and the browser shows it again afterwards."""
    env = {"CICLONE_SYNC": "0", "CICLONE_SPEED": "1", "CICLONE_SD_DELAY_US": "20000"}
    sd = _card(t, {SRM1: b"\x5a" * 2048}, extra={"/Test Game.cov": (_cov(), T0)})
    m = t.menu(sd, env=env)
    m.goto("Test Game.sfc")
    m.step(6)
    m.press("Y")
    m.step(20)
    _bar_to_label(m, "text_filesel_context_saves")
    m.press("A")
    m.wait(lambda: m.has(c.tr("text_saves_date")), what="a tela de Saves")
    m.step(60)
    assert m.u8("cover_loaded") == 0, "a capa ficou por cima da tela de Saves"
    m.press("B")
    m.wait(lambda: m.u8("cover_loaded") == 1, frames=1800, what="a capa de volta no navegador")
    m.close()


def test_mouse_points_at_slots_and_rests_on_a_header(t):
    """The pointer on a slot row moves the bar there; resting on a header leaves the bar
    alone (it would bounce over the line it can never reach); a click opens the actions."""
    import test_mouse as tm
    sd = _card(t, {SRM1: b"\x5a" * 2048})
    m = t.menu(sd, env=tm.MOUSE)
    m.goto("Test Game.sfc", pad=2)
    m.press("Y", pad=2)
    m.settle()
    want = c.tr("text_filesel_context_saves")
    for _ in range(12):
        if want in m.bar_row():
            break
        m.press("DOWN", pad=2)
        m.step(8)
    m.press("A", pad=2)
    _wait_rows(m)
    row = lambda kind, n: 8 * _slot_row(m, kind, n) - 10      # text row -> pointer line
    tm._point(m, 200, row("text_saves_state", 2))
    m.step(30)
    assert m.u8("bar_yl") + 1 == _slot_row(m, "text_saves_state", 2), m.text()
    head = _slot_row(m, "text_saves_state", 1) - 1
    tm._point(m, 200, 8 * head - 10)
    bars = set()
    for _ in range(20):
        m.step(3)
        bars.add(m.u8("bar_yl"))
    assert len(bars) == 1, f"a barra oscilou sobre o cabeçalho: {sorted(bars)}"
    tm._point(m, 200, row("text_saves_srm", 1))
    m.step(30)
    m.mouse_click("left")
    m.wait_text(c.tr("text_saves_copy"))        # the actions of a slot that has a save
    m.close()


def test_the_levels_below_stay_greyed(t):
    """The actions open over the list and a copy's destinations over the actions: what is
    under the open level stays on screen, greyed; closing it brings the colours back."""
    sd = _card(t, {SRM1: b"\x11" * 2048})
    m = t.menu(sd)
    _open_from_browser(m)
    assert _pal(m, "text_saves_srm", 2) == 0
    y = _slot_row(m, "text_saves_state", 4)          # a row the next levels leave in sight
    x = m.screen()[y].index(c.tr("text_saves_slot"))
    _bar_to_slot(m, "text_saves_srm", 1)
    m.press("A")
    m.wait_text(c.tr("text_saves_copy"))
    m.settle()
    assert m.tile_at(x, y)[1] == GREY, "a lista não ficou cinza sob as ações\n" + m.text()
    yt = _slot_row(m, "text_saves_srm", 1) + 1       # the actions' title ("Slot 1"), on their
    xt = m.screen()[yt].index(c.tr("text_saves_slot"))   # top border just below the row
    _bar_to_label(m, "text_saves_copy")
    m.press("A")
    m.settle()
    assert m.tile_at(xt, yt)[1] == GREY, "as ações não ficaram cinza sob os destinos\n" + m.text()
    m.press("B")                                     # out of the destinations and the actions
    m.settle()
    assert m.tile_at(x, y)[1] == 0 and _starts(m, "text_saves_srm", 1), m.text()
    m.close()
