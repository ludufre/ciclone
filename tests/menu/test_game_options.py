"""Opcoes do jogo: o que vale so para um jogo por cima de uma opcao global (hoje a correcao 1CHIP),
gravado em /sd2snes/saves/<BB>/<stem>.opt (um byte por opcao: '-' padrao, '0' desligado, '1' ligado).

No menu: a linha "Opcoes do jogo" dos tres menus de contexto (navegador, Recentes, Favoritos) e o L
da ficha abrem a tela; o valor muda no lugar e sai para o cartao quando a tela fecha. No jogo: Y na
barra do menu in-game abre a tela, e cada mudanca vai na hora para o cartao E para o FPGA (o bit
$2100 das features). Na carga, o .opt do jogo decide; sem ele, a opcao global."""
import re

import ciclone as c
import test_games as tg

OPT = "/sd2snes/saves/TE/Test Game.opt"
SMW_OPT = "/sd2snes/saves/SU/Super Mario World.opt"
FEAT_2100 = 0x40


def _bar_to(m, label, tries=16):
    want = c.tr(label)
    for _ in range(tries):
        if want in m.bar_row():
            return
        m.press("DOWN")
        m.step(8)
    raise c.MenuError(f"{label} nao esta na lista\n{m.text()}")


def _wait_screen(m):
    m.wait(lambda: m.has(c.tr("mtext_ingame_1chiptransientfixes")), what="a tela de opcoes do jogo")
    m.settle()


def _set_value(m, label):
    """A na linha da opcao edita o valor no lugar; UP avanca, DOWN volta (sem dar a volta:
    Padrao, Ligado, Desligado); A confirma."""
    _bar_to(m, "mtext_ingame_1chiptransientfixes")
    m.press("A")
    m.settle()
    want = c.tr(label)
    # "Default (Off)" carries the word Off too: match the value as the row's last word(s)
    is_it = lambda: (m.bar_row().rstrip().endswith(want)                      # noqa: E731
                     and (label == "text_gopt_default") == ("(" in m.bar_row()))
    if label == "text_gopt_default":
        is_it = lambda: want + " (" in m.bar_row()                            # noqa: E731
    for btn in ("UP", "UP", "DOWN", "DOWN", "DOWN"):
        if is_it():
            break
        m.press(btn)
        m.step(10)
    assert is_it(), m.text()
    m.press("A")
    m.settle()


def _from_context(m):
    m.press("Y")
    m.settle()
    _bar_to(m, "mtext_gopt_row")
    m.press("A")
    _wait_screen(m)


def _features_at_boot(m):
    """O ultimo 'set features' antes do laco do jogo."""
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot da ROM")
    log = m.fwlog()
    log = log[:log.index("going to snes main loop")]
    vals = re.findall(r"set features: ([0-9a-f]{4})", log)
    assert vals, log[-2000:]
    return int(vals[-1], 16)


def _boot_test_game(t, config=None, extra=None):
    sd = t.sd(config=config, extra=extra)
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")
    return m


def test_browser_row_writes_the_opt(t):
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    want = f'{c.tr("text_gopt_default")} ({c.tr("text_off")})'   # what the global gives today
    assert m.has(want), m.text()
    _set_value(m, "text_on")
    m.press("B")                                   # fecha a tela: e aqui que o .opt e gravado
    m.settle()
    assert t.read(sd, OPT) == b"1", t.read(sd, OPT)
    m.goto("Test Game.sfc")                        # reaberta, mostra o que esta no cartao
    _from_context(m)
    _bar_to(m, "mtext_ingame_1chiptransientfixes")
    assert c.tr("text_on") in m.bar_row(), m.text()
    _set_value(m, "text_gopt_default")             # de volta ao padrao: o arquivo some
    m.press("B")
    m.settle()
    m.close()
    assert t.read(sd, OPT) is None, t.read(sd, OPT)


def test_the_row_is_only_on_games(t):
    """Uma pasta tem menu de contexto (as linhas do gerenciador de arquivos), mas nao a do jogo."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Two Games/")
    m.press("Y")
    m.settle()
    assert not m.has(c.tr("mtext_gopt_row")), m.text()
    m.close()


def test_from_recents(t):
    sd = t.sd(extra={"/sd2snes/lastgame.cfg": b"/Test Game.sfc\0"})
    m = t.menu(sd)
    m.press("START")
    m.wait_text(c.tr("text_last"))
    _from_context(m)
    _set_value(m, "text_off")
    m.press("B")
    m.settle()
    m.close()
    assert t.read(sd, OPT) == b"0", t.read(sd, OPT)


def test_from_favorites(t):
    sd = t.sd(extra={"/sd2snes/favorites.cfg": b"/Test Game.sfc\0"})
    m = t.menu(sd)
    m.press("SEL")
    m.wait_text(c.tr("text_favorite"))
    _from_context(m)
    _set_value(m, "text_on")
    m.press("B")
    m.settle()
    m.close()
    assert t.read(sd, OPT) == b"1", t.read(sd, OPT)


def test_l_on_the_info_screen(t):
    sd = t.sd(extra={OPT: b"0"})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("L")
    _wait_screen(m)
    _bar_to(m, "mtext_ingame_1chiptransientfixes")
    assert c.tr("text_off") in m.bar_row(), m.text()
    _set_value(m, "text_on")
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de volta")
    m.close()
    assert t.read(sd, OPT) == b"1", t.read(sd, OPT)


RECENTS2 = {"/sd2snes/lastgame.cfg": b"/MSU Game/msugame.sfc\0/Test Game.sfc\0"}


def _recents_ficha_second(m):
    """Recentes -> 2a linha -> A: a ficha do Test Game (entrada 1 da lista)."""
    m.press("START")
    m.wait_text(c.tr("text_last"))
    m.press("DOWN")
    m.step(10)
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Test Game"), what="a ficha")
    m.settle()


def test_l_from_a_recents_ficha_comes_back_to_the_same_game(t):
    """A ficha de Recentes e reconstruida pelo indice da lista: depois do L ela tem que voltar
    no MESMO jogo, e uma nova mudanca vai para o .opt dele."""
    sd = t.sd(extra=RECENTS2)
    m = t.menu(sd)
    _recents_ficha_second(m)
    m.press("L")
    _wait_screen(m)
    _set_value(m, "text_on")
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de volta")
    m.settle()
    assert m.has("Test Game") and not m.has("msugame"), m.text()
    m.close()
    assert t.read(sd, OPT) == b"1", t.read(sd, OPT)


def test_r_from_a_recents_ficha_comes_back_to_the_same_game(t):
    sd = t.sd(extra=RECENTS2)
    m = t.menu(sd)
    _recents_ficha_second(m)
    m.press("R")
    m.wait(lambda: m.has(c.tr("text_saves_date")), what="a tela de Saves")
    m.settle()
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de volta")
    m.settle()
    assert m.has("Test Game") and not m.has("msugame"), m.text()
    m.close()


def test_the_opt_decides_at_load(t):
    """Ligado no .opt com a global desligada: o bit $2100 vai para o FPGA."""
    m = _boot_test_game(t, extra={OPT: b"1"})
    assert _features_at_boot(m) & FEAT_2100
    m.close()


def test_off_in_the_opt_beats_the_global(t):
    m = _boot_test_game(t, config="---\n1CHIPTransientFixes: true\n", extra={OPT: b"0"})
    assert not _features_at_boot(m) & FEAT_2100
    m.close()


def test_without_opt_the_global_decides(t):
    m = _boot_test_game(t, config="---\n1CHIPTransientFixes: true\n")
    assert _features_at_boot(m) & FEAT_2100
    m.close()


def test_unknown_bytes_of_a_newer_firmware_are_kept(t):
    """Um firmware so reescreve o byte da opcao que conhece."""
    sd = t.sd(extra={OPT: b"-7"})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    _set_value(m, "text_on")
    m.press("B")
    m.settle()
    m.close()
    assert t.read(sd, OPT) == b"17", t.read(sd, OPT)


def _last_features(m):
    vals = re.findall(r"set features: ([0-9a-f]{4})", m.fwlog())
    return int(vals[-1], 16)


def _ovl_glyph(m, x, y):
    base = 0x5000 if x % 2 == 0 else 0x5800
    w = m.peek("vram", (base + y * 32 + x // 2) * 2, 2)
    w = w[0] | w[1] << 8
    return (w & 0x3FF) >> 1, w >> 10 & 7


def _sides_intact(m, needle, pal=3):
    """The row with `needle` still has its window's two side borders (glyphs 26 / 27, frame
    palette 3): a redraw of the whole row used to wipe them."""
    lines = tg._ovl_text(m).splitlines()
    y = next(i for i, r in enumerate(lines) if needle in r)
    cells = [_ovl_glyph(m, x, y) for x in range(64)]
    left = [x for x, (g, _) in enumerate(cells) if g == 26]
    right = [x for x, (g, _) in enumerate(cells) if g == 27]
    assert len(left) == 1 and len(right) == 1, (needle, left, right)
    assert cells[left[0]][1] == pal and cells[right[0]][1] == pal, (needle, cells[left[0]], cells[right[0]])
    return left[0], right[0]


def _ingame_gopt(t):
    m = tg._smw_in_yoshis_house(t)
    m.hold(*m.menu_combo())
    m.step(20)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == tg.TAB_ON, frames=120, what="o menu in-game")
    m.press("Y", hold=6, after=60)
    m.wait(lambda: "Game options" in tg._ovl_text(m), frames=120, what="a tela de opcoes do jogo")
    return m


def _edit_to(m, presses):
    """A edita (a barra vira o campo do valor), as setas trocam, A confirma."""
    m.press("A", hold=6, after=30)
    for btn in presses:
        m.press(btn, hold=6, after=30)


def test_ingame_y_changes_it_live(t):
    """Y na barra do menu in-game abre a tela, que se comporta como as listas de opcoes do menu:
    A edita, Cima/Baixo trocam o valor so na tela, A grava (o .opt e o bit $2100 do FPGA mudam
    na hora), B cancela sem mudar nada."""
    m = _ingame_gopt(t)
    text = tg._ovl_text(m)
    assert "1CHIP transient fixes" in text and "Default (Off)" in text, text
    assert not _last_features(m) & FEAT_2100
    sd = m.sd
    n = m.fwlog().count("gameopt ")
    m.press("A", hold=6, after=30)                 # edit: Up = On, but nothing is sent yet
    m.press("UP", hold=6, after=30)
    m.wait(lambda: re.search(r"fixes\s+On\b", tg._ovl_text(m)), frames=120, what="a previa On")
    assert m.fwlog().count("gameopt ") == n and not _last_features(m) & FEAT_2100
    m.press("B", hold=6, after=60)                 # B cancels: back to Default, screen stays
    m.wait(lambda: "Default (Off)" in tg._ovl_text(m), frames=120, what="o valor de antes")
    assert "Game options" in tg._ovl_text(m) and m.fwlog().count("gameopt ") == n
    m.press("A", hold=6, after=30)                 # On, for real
    m.press("UP", hold=6, after=30)
    m.press("A", hold=6, after=90)
    m.wait(lambda: _last_features(m) & FEAT_2100, frames=300, what="o bit $2100 ligado")
    assert re.search(r"fixes\s+On\b", tg._ovl_text(m)), tg._ovl_text(m)
    m.step(10)
    wl, wr = _sides_intact(m, "1CHIP transient fixes")
    dl, dr = _sides_intact(m, "Takes effect now", pal=1)      # the description box is greyed
    assert wl == dl, (wl, dl)                                  # same left edge, own widths
    assert wr != dr, (wr, dr)
    m.press("A", hold=6, after=30)
    m.shot(c.ROOT / "build" / "igopt_edit.png")
    m.press("UP", hold=6, after=30)                # Off
    m.press("A", hold=6, after=90)
    m.wait(lambda: re.search(r"fixes\s+Off\b", tg._ovl_text(m)), frames=300, what="o valor Off")
    assert not _last_features(m) & FEAT_2100
    m.shot(c.ROOT / "build" / "igopt.png")
    m.press("A", hold=6, after=30)                 # L = the first value: Default
    m.press("L", hold=6, after=30)
    m.press("A", hold=6, after=90)
    m.wait(lambda: "Default (Off)" in tg._ovl_text(m), frames=300, what="de volta ao padrao")
    m.press("Y", hold=6, after=60)                 # Y fecha e volta para a aba de onde veio
    m.wait(lambda: "Game options" not in tg._ovl_text(m), frames=120, what="a aba de baixo")
    m.press("B", hold=6, after=60)
    m.step(60)
    tg._walk_right(m)
    m.close()
    assert t.read(sd, SMW_OPT) is None


def test_ingame_help_and_footer_name_y(t):
    """O rodape da barra anuncia o Y, e a AJUDA (SELECT) tem a linha dele."""
    m = tg._smw_in_yoshis_house(t)
    m.hold(*m.menu_combo())
    m.step(20)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == tg.TAB_ON, frames=120, what="o menu in-game")
    assert "Y:OPTIONS" in tg._ovl_text(m), tg._ovl_text(m)
    m.press("SEL", hold=6, after=60)
    m.wait(lambda: "options for this game" in tg._ovl_text(m), frames=120, what="a AJUDA")
    m.close()


def test_ingame_on_is_written(t):
    m = _ingame_gopt(t)
    sd = m.sd
    m.press("A", hold=6, after=30)
    m.press("UP", hold=6, after=30)
    m.press("A", hold=6, after=90)
    m.wait(lambda: re.search(r"fixes\s+On\b", tg._ovl_text(m)), frames=300, what="o valor On")
    m.press("START", hold=6, after=60)             # START fecha tudo direto
    m.step(60)
    tg._walk_right(m)
    m.close()
    assert t.read(sd, SMW_OPT) == b"1", t.read(sd, SMW_OPT)
