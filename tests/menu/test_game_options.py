"""Opcoes do jogo: as opcoes do config.yml que um jogo sobrepoe, e o slot do save / do savestate
com que ele comeca, em /sd2snes/saves/<BB>/<stem>.yml (as MESMAS chaves do config.yml, mais
SaveGameSlot / SaveStateSlot; chave ausente ou -1 = segue a global).

Quais opcoes: gameopt_list no firmware (src/gameopt.c). As telas mostram cada uma dentro do
submenu de Configuracoes em que a linha dela mora, com o nome, a descricao e os valores da
propria linha, e "Padrao (<o que a global da>)" na frente.

No menu: a linha "Opcoes do jogo" dos tres menus de contexto (navegador, Recentes, Favoritos;
sair da tela VOLTA ao menu de contexto) e o L da ficha abrem a tela: submenus como em
Configuracoes, e o valor sai para o cartao quando a tela fecha. No jogo: Y na barra do menu
in-game abre a mesma arvore; o que muda o jogo em execucao aparece apagado e nao edita, e o que
pode mudar (1CHIP, limite de brilho...) vai na hora para o cartao E para o FPGA."""
import re

import ciclone as c
import test_games as tg

YML = "/sd2snes/saves/TE/Test Game.yml"
SLOT = "/sd2snes/saves/TE/Test Game.slot"
SMW_YML = "/sd2snes/saves/SU/Super Mario World.yml"
FEAT_2100 = 0x40


def _bar_to(m, label, tries=24):
    want = c.tr(label)
    for _ in range(tries):
        if want in m.bar_row():
            return
        m.press("DOWN")
        m.step(8)
    raise c.MenuError(f"{label} nao esta na lista\n{m.text()}")


def _wait_screen(m):
    """A tela abre nos grupos: os submenus de Configuracoes que tem opcoes por jogo."""
    m.wait(lambda: m.has(c.tr("mtext_cfg_ingame")) and m.has(c.tr("mtext_gopt_row")),
           what="a tela de opcoes do jogo")
    m.settle()


def _open_ingame_group(m):
    _bar_to(m, "mtext_cfg_ingame")
    m.press("A")
    m.wait(lambda: m.has(c.tr("mtext_ingame_1chiptransientfixes")), what="o grupo In-game")
    m.settle()


def _set_value(m, row, label):
    """A na linha edita o valor no lugar (o dialogo de valor do menu): UP avanca, DOWN volta,
    sem dar a volta (Padrao, Ligado, Desligado); A confirma."""
    _bar_to(m, row)
    m.press("A")
    m.settle()
    want = c.tr(label)
    if label == "text_gopt_default":
        is_it = lambda: want + " (" in m.bar_row()                            # noqa: E731
    else:
        is_it = lambda: (m.bar_row().rstrip().endswith(want)                  # noqa: E731
                         and "(" not in m.bar_row())
    for btn in ("UP", "UP", "DOWN", "DOWN", "DOWN"):
        if is_it():
            break
        m.press(btn)
        m.step(10)
    assert is_it(), m.text()
    m.press("A")
    m.settle()


def _close_screen(m):
    """B fecha o grupo, B fecha a tela: e aqui que o arquivo e gravado."""
    m.press("B")
    m.settle()
    m.press("B")
    m.settle()


def _from_context(m):
    m.press("Y")
    m.settle()
    _bar_to(m, "mtext_gopt_row")
    m.press("A")
    _wait_screen(m)


def _lines(data):
    return [ln for ln in data.decode().replace("\r", "").split("\n") if ln and ln != "---"]


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


def test_browser_row_writes_the_yml(t):
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    _open_ingame_group(m)
    want = f'{c.tr("text_gopt_default")} ({c.tr("text_off")})'   # what the global gives today
    assert m.has(want), m.text()
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_on")
    _close_screen(m)
    assert _lines(t.read(sd, YML)) == ["1CHIPTransientFixes: true"], t.read(sd, YML)
    m.press("B")                                   # (the context menu is still up: see below)
    m.settle()
    m.goto("Test Game.sfc")                        # reaberta, mostra o que esta no cartao
    _from_context(m)
    _open_ingame_group(m)
    _bar_to(m, "mtext_ingame_1chiptransientfixes")
    assert m.bar_row().rstrip().endswith(c.tr("text_on")), m.text()
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_gopt_default")
    _close_screen(m)                               # de volta ao padrao: o arquivo some
    m.close()
    assert t.read(sd, YML) is None, t.read(sd, YML)


def test_leaving_comes_back_to_the_context_menu(t):
    """A linha e um MTYPE_FUNC: fechar a tela de opcoes volta ao menu de contexto, nao ao
    navegador."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    m.press("B")
    m.settle()
    assert c.tr("mtext_gopt_row") in m.bar_row(), m.text()   # the context menu, on our row
    assert not m.has(c.tr("mtext_cfg_ingame")), m.text()
    m.close()


def _right_edge(m, needle):
    """The column of the last non-blank cell on the screen row that has `needle`."""
    row = next(r for r in m.screen() if needle in r)
    return len(row.rstrip()) - 1


def test_groups_are_the_settings_submenus(t):
    """Os grupos sao os submenus de Configuracoes que tem opcao para ESTE jogo: um jogo de
    SNES sem chip nem .msu nao ve Chip nem SGB (e os submenus sem opcao por jogo -- o
    navegador, o BS-X, o tour -- nunca aparecem)."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    for lbl in ("mtext_cfg_ingame", "mtext_cfg_savestates", "mtext_cfg_scic"):
        assert m.has(c.tr(lbl)), (lbl, m.text())
    for lbl in ("mtext_cfg_chip", "mtext_cfg_sgb", "mtext_cfg_browser", "mtext_cfg_bsx",
                "mtext_cfg_tour"):
        assert not m.has(c.tr(lbl)), (lbl, m.text())
    m.close()


def test_msu_game_has_the_msu_options(t):
    """Com um .msu ao lado, o grupo de chips aparece so com o volume do MSU-1, e o autosave
    do MSU-1 entra no grupo do jogo."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("MSU Game/")
    m.press("A")                                   # a MSU-1 folder opens as the game
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("L")
    _wait_screen(m)
    assert m.has(c.tr("mtext_cfg_chip")), m.text()
    _bar_to(m, "mtext_cfg_chip")
    m.press("A")
    m.wait(lambda: m.has(c.tr("mtext_chip_msu1_volume_boost")), what="o volume do MSU-1")
    assert not m.has(c.tr("mtext_chip_cx4_speed")) and not m.has(c.tr("mtext_chip_gsu_speed")), m.text()
    m.close()


GB = {"/Pocket Game.gb": b"\0" * 0x8000}


def test_game_boy_shows_sgb_and_fits(t):
    """Um jogo de Game Boy ve o grupo SGB (com a rotacao dos botoes) e nao as opcoes do
    nucleo SNES; a janela do grupo cabe na tela e a barra anda nela."""
    sd = t.sd(extra=GB)
    m = t.menu(sd)
    m.goto("Pocket Game.gb")
    _from_context(m)
    assert m.has(c.tr("mtext_cfg_sgb")), m.text()
    _bar_to(m, "mtext_cfg_sgb")
    m.press("A")
    m.wait(lambda: m.has(c.tr("mtext_gb_rotate")), what="o grupo SGB")
    m.settle()
    m.shot(c.ROOT / "build" / "gopt_menu_sgb.png")
    assert c.tr("mtext_sgb_enable_hooks") in m.bar_row(), m.text()      # the bar is on row 1
    for _ in range(3):
        m.press("DOWN")
        m.step(8)
    assert c.tr("mtext_sgb_spr_increase") in m.bar_row() or m.bar_row().strip(), m.text()
    for needle in (c.tr("mtext_sgb_clock"), c.tr("mtext_gb_rotate"), c.tr("mtext_gbc_mode")):
        if m.has(needle):
            assert _right_edge(m, needle) <= 62, (needle, m.text())
    assert not m.has(c.tr("mtext_ingame_1chiptransientfixes")), m.text()
    m.press("B")
    m.settle()
    assert not m.has(c.tr("mtext_cfg_savestates")), m.text()            # no SNES savestates
    m.close()


def test_game_boy_ingame_group_shows_what_its_cores_use(t):
    """Num jogo de Game Boy o grupo In-game mostra o que um dos dois nucleos dele usa: o SGB
    roda a BIOS do SGB (um programa de SNES, com o hook, os gestos e o patch de $2100 do
    cheat.v), o GBC roda o nosso player. O que so o SGB usa leva "(SGB)" depois do nome; o que
    so os nucleos de SNES tem (controle 2, menu in-game, $213F, temporizacao do barramento,
    MSU-1) nao aparece."""
    sd = t.sd(extra=GB)
    m = t.menu(sd)
    m.goto("Pocket Game.gb")
    _from_context(m)
    _open_ingame_group(m)
    m.shot(c.ROOT / "build" / "gopt_menu_gb_ingame.png")
    src = (c.SD2SNES / "snes" / "const.a65").read_text(errors="replace")

    def name(lbl):   # the label's text without the sub-row mark (c.tr stops at that byte)
        line = re.search(rf"^{lbl}\s+\.byt\s+(.*)$", src, re.M).group(1)
        return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', line)).strip()
    for lbl in ("mtext_ingame_enable", "mtext_ingame_buttons", "mtext_ingame_holdoff",
                "mtext_ingame_1chiptransientfixes", "mtext_ingame_brightlimit",
                "mtext_ingame_resetpatch"):          # the GBC core's cheat.v is dead
        assert m.has(name(lbl) + " (SGB)"), (lbl, m.text())
    for lbl in ("mtext_ingame_autosave", "mtext_ingame_shortreset"):
        assert m.has(name(lbl)) and not m.has(name(lbl) + " (SGB)"), (lbl, m.text())
    for lbl in ("mtext_ingame_pad2", "mtext_ingame_cheat_overlay", "mtext_ingame_regionpatch",
                "mtext_scic_buscompat", "mtext_ingame_autosave_msu1"):
        assert not m.has(name(lbl)), (lbl, m.text())
    assert _right_edge(m, name("mtext_ingame_1chiptransientfixes")) <= 62, m.text()
    m.press("B")
    m.settle()
    m.close()


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
    _open_ingame_group(m)
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_off")
    _close_screen(m)
    assert c.tr("mtext_gopt_row") in m.bar_row(), m.text()   # back on Recents' context menu
    m.close()
    assert _lines(t.read(sd, YML)) == ["1CHIPTransientFixes: false"], t.read(sd, YML)


def test_from_favorites(t):
    sd = t.sd(extra={"/sd2snes/favorites.cfg": b"/Test Game.sfc\0"})
    m = t.menu(sd)
    m.press("SEL")
    m.wait_text(c.tr("text_favorite"))
    _from_context(m)
    _open_ingame_group(m)
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_on")
    _close_screen(m)
    # back on the context menu = the screen's GOOP_SETs are done (the file is written)
    m.wait(lambda: c.tr("mtext_gopt_row") in m.bar_row(), what="o menu de contexto dos Favoritos")
    m.close()
    assert _lines(t.read(sd, YML)) == ["1CHIPTransientFixes: true"], t.read(sd, YML)


def test_l_on_the_info_screen(t):
    sd = t.sd(extra={YML: b"---\r\n1CHIPTransientFixes: false\r\n"})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("L")
    _wait_screen(m)
    _open_ingame_group(m)
    _bar_to(m, "mtext_ingame_1chiptransientfixes")
    assert m.bar_row().rstrip().endswith(c.tr("text_off")), m.text()
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_on")
    _close_screen(m)
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de volta")
    m.close()
    assert _lines(t.read(sd, YML)) == ["1CHIPTransientFixes: true"], t.read(sd, YML)


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
    no MESMO jogo, e uma nova mudanca vai para o arquivo dele."""
    sd = t.sd(extra=RECENTS2)
    m = t.menu(sd)
    _recents_ficha_second(m)
    m.press("L")
    _wait_screen(m)
    _open_ingame_group(m)
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_on")
    _close_screen(m)
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de volta")
    m.settle()
    assert m.has("Test Game") and not m.has("msugame"), m.text()
    m.close()
    assert _lines(t.read(sd, YML)) == ["1CHIPTransientFixes: true"], t.read(sd, YML)


def test_the_yml_decides_at_load(t):
    """Ligado no arquivo do jogo com a global desligada: o bit $2100 vai para o FPGA."""
    m = _boot_test_game(t, extra={YML: b"---\r\n1CHIPTransientFixes: true\r\n"})
    assert _features_at_boot(m) & FEAT_2100
    m.close()


def test_off_in_the_yml_beats_the_global(t):
    m = _boot_test_game(t, config="---\n1CHIPTransientFixes: true\n",
                        extra={YML: b"---\r\n1CHIPTransientFixes: false\r\n"})
    assert not _features_at_boot(m) & FEAT_2100
    m.close()


def test_minus_one_follows_the_global(t):
    m = _boot_test_game(t, config="---\n1CHIPTransientFixes: true\n",
                        extra={YML: b"---\r\n1CHIPTransientFixes: -1\r\n"})
    assert _features_at_boot(m) & FEAT_2100
    m.close()


def test_without_yml_the_global_decides(t):
    m = _boot_test_game(t, config="---\n1CHIPTransientFixes: true\n")
    assert _features_at_boot(m) & FEAT_2100
    m.close()


def test_the_game_values_never_reach_config_yml(t):
    """Com o jogo carregado, o CFG tem os valores do jogo; o config.yml so recebe a global."""
    m = _boot_test_game(t, extra={YML: b"---\r\n1CHIPTransientFixes: true\r\nBrightnessLimit: 7\r\n"})
    _features_at_boot(m)
    sd = m.sd
    m.close()
    cfg = t.read(sd, "/sd2snes/config.yml").decode()
    assert "1CHIPTransientFixes: false" in cfg and "BrightnessLimit: 15" in cfg, cfg


def test_unknown_keys_and_slots_are_kept(t):
    """Uma chave que este firmware nao conhece (de um mais novo, do Web Manager) e as dos
    slots ficam no arquivo quando uma opcao muda."""
    sd = t.sd(extra={YML: b"---\r\nFutureKey: 7\r\nSaveGameSlot: 3\r\n"})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    _open_ingame_group(m)
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_on")
    _close_screen(m)
    m.close()
    lines = _lines(t.read(sd, YML))
    assert "FutureKey: 7" in lines and "SaveGameSlot: 3" in lines, lines
    assert "1CHIPTransientFixes: true" in lines, lines


def test_the_slot_of_before_is_read_and_moved(t):
    """O .slot de antes (byte 0 o save, byte 1 o savestate) vale enquanto o arquivo do jogo nao
    diz nada, e some na primeira gravacao (os slots passam para o .yml)."""
    sd = t.sd(extra={SLOT: b"24"})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    _open_ingame_group(m)
    _set_value(m, "mtext_ingame_1chiptransientfixes", "text_on")
    _close_screen(m)
    m.close()
    lines = _lines(t.read(sd, YML))
    assert "SaveGameSlot: 2" in lines and "SaveStateSlot: 4" in lines, lines
    assert t.read(sd, SLOT) is None


# ---- in game -------------------------------------------------------------------------------

def _last_features(m):
    vals = re.findall(r"set features: ([0-9a-f]{4})", m.fwlog())
    return int(vals[-1], 16)


def _ingame_gopt(t, extra=None):
    m = tg._smw_in_yoshis_house(t, extra=extra)
    m.hold(*m.menu_combo())
    m.step(20)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == tg.TAB_ON, frames=120, what="o menu in-game")
    m.press("Y", hold=6, after=60)
    m.wait(lambda: "Game options" in tg._ovl_text(m) and "In-game Settings" in tg._ovl_text(m),
           frames=180, what="a tela de opcoes do jogo")
    return m


def _ingame_group(m, first="Reset to menu"):
    """A on the groups until the one whose first row is `first` opens (Settings' order: the
    In-game group is the third)."""
    for _ in range(8):
        m.press("A", hold=6, after=90)
        if first in tg._ovl_text(m):
            return
        m.press("B", hold=6, after=90)
        m.press("DOWN", hold=6, after=30)
    raise AssertionError(tg._ovl_text(m))


def _down_to(m, needle, tries=16):
    for _ in range(tries):
        if needle in tg._ovl_text(m):
            return
        m.press("DOWN", hold=6, after=40)
    raise AssertionError(tg._ovl_text(m))


def test_ingame_y_changes_it_live(t):
    """Y na barra do menu in-game abre os grupos; A abre um. Uma opcao que pode mudar com o jogo
    rodando edita como no menu (A, Cima/Baixo na ordem da tabela da linha, A grava: o arquivo e o bit $2100 mudam na hora;
    B cancela)."""
    m = _ingame_gopt(t)
    _ingame_group(m)
    assert not _last_features(m) & FEAT_2100
    sd = m.sd
    # the bar onto the 1CHIP row: the 9th of the group (Settings' own order, without the rows
    # that are not this game's options)
    for _ in range(8):
        m.press("DOWN", hold=6, after=40)
    m.wait(lambda: "Patch brightness" in tg._ovl_text(m), frames=120, what="a descricao do 1CHIP")
    text = tg._ovl_text(m)
    assert re.search(r"1CHIP transient fixes\s+Default \(Off\)", text), text
    n = m.fwlog().count("gameopt ")
    m.press("A", hold=6, after=30)                 # edit: Up = the next value (Off, the order of
    m.press("UP", hold=6, after=30)                #   the Settings row's own table), nothing sent
    m.wait(lambda: re.search(r"fixes\s+Off\b", tg._ovl_text(m)), frames=120, what="a previa Off")
    m.press("B", hold=6, after=60)                 # B cancels: back to Default, screen stays
    m.wait(lambda: re.search(r"fixes\s+Default \(Off\)", tg._ovl_text(m)), frames=120,
           what="o valor de antes")
    assert m.fwlog().count("gameopt ") == n
    m.press("A", hold=6, after=30)                 # On, for real: Default, Off, On
    m.press("UP", hold=6, after=30)
    m.press("UP", hold=6, after=30)
    m.press("A", hold=6, after=90)
    m.wait(lambda: _last_features(m) & FEAT_2100, frames=300, what="o bit $2100 ligado")
    assert re.search(r"fixes\s+On\b", tg._ovl_text(m)), tg._ovl_text(m)
    m.shot(c.ROOT / "build" / "igopt.png")
    m.press("START", hold=6, after=60)             # START fecha tudo direto
    m.step(60)
    tg._walk_right(m)
    m.close()
    assert "1CHIPTransientFixes: true" in _lines(t.read(sd, SMW_YML)), t.read(sd, SMW_YML)


def test_ingame_locked_rows_do_not_change(t):
    """O hook in-game so vale na carga: a linha aparece apagada, o A nao edita, e a caixa diz
    para mudar pelo menu."""
    m = _ingame_gopt(t)
    _ingame_group(m)
    _down_to(m, "In-game hook")
    for _ in range(6):
        if "Change it from the menu" in tg._ovl_text(m):
            break
        m.press("DOWN", hold=6, after=40)
    assert "Change it from the menu" in tg._ovl_text(m), tg._ovl_text(m)
    n = m.fwlog().count("gameopt ")
    m.press("A", hold=6, after=30)
    m.press("UP", hold=6, after=30)
    m.press("A", hold=6, after=60)
    assert m.fwlog().count("gameopt ") == n, "a locked row sent a change"
    m.close()


def test_ingame_b_goes_back_a_level(t):
    m = _ingame_gopt(t)
    _ingame_group(m)
    m.press("B", hold=6, after=90)                 # back to the groups
    m.wait(lambda: "Autosave" not in tg._ovl_text(m), frames=120, what="os grupos")
    assert "Game options" in tg._ovl_text(m), tg._ovl_text(m)
    m.press("B", hold=6, after=90)                 # and out of the screen
    m.wait(lambda: "Game options" not in tg._ovl_text(m), frames=120, what="a aba de baixo")
    m.close()


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


def test_menu_and_ingame_draw_the_same_screen(t):
    """A mesma tela (o grupo Savestates de um jogo de SNES sem chip) no menu e no jogo: as
    janelas nos mesmos lugares e tamanhos, a de cima sobre a de grupos, a caixa de descricao
    na mesma borda esquerda. Os PNGs ficam em build/gopt_same_{menu,ingame}.png."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    _from_context(m)
    _bar_to(m, "mtext_cfg_savestates")
    m.press("A")
    m.wait(lambda: m.has(c.tr("mtext_savestate_slots")), what="o grupo Savestates")
    m.settle()
    m.shot(c.ROOT / "build" / "gopt_same_menu.png")
    m0 = m.screen()
    rows = [r for r in m0 if c.tr("mtext_ingame_savestate") in r]
    m.close()
    m = _ingame_gopt(t)
    _ingame_group(m, first="In-game savestates")
    m.step(30)
    m.shot(c.ROOT / "build" / "gopt_same_ingame.png")
    ing = tg._ovl_text(m).splitlines()
    (c.ROOT / "build" / "gopt_same.txt").write_text("\n".join(m0) + "\n=====\n" + "\n".join(ing))
    for r in rows:                               # the same text in the same columns
        key = r.strip()[:12]
        hit = [x for x in ing if key in x]
        assert hit and hit[0].index(key) == r.index(key), (r, hit)
    m.close()
    # and on the screen: the group window's frame in the same pixel columns, its bottom border
    # within the 3 lines the menu's scrolled text area leaves (8-line rows)
    from PIL import Image

    def frame(path):
        im = Image.open(path).convert("RGB")
        blue = lambda p: p[2] > 180 and p[1] > 150 and p[0] < 200          # noqa: E731
        ys = [y for y in range(im.size[1])
              if sum(blue(im.getpixel((x, y))) for x in range(150, 300)) > 120]
        y = ys[-1] - 4
        xs = [x for x in range(im.size[0]) if blue(im.getpixel((x, y)))]
        return ys[-1], xs[0], xs[-1]
    mb, ml, mr = frame(c.ROOT / "build" / "gopt_same_menu.png")
    ib, il, ir = frame(c.ROOT / "build" / "gopt_same_ingame.png")
    assert (ml, mr) == (il, ir), ((ml, mr), (il, ir))
    assert abs(mb - ib) <= 4, (mb, ib)
