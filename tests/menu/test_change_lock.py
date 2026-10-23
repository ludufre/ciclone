"""The parental lock (snes/lock.a65 + fmres.a65): a code of 4 to 10 pad buttons (LockCode in
config.yml, the buttons as letters in order, "BYsSudlrAXLR"; 5 bytes of nibbles in CFG, B=1 Y=2
Select=3 Start=4 ... R=12) asked before what changes the card or the settings.  Each button
counts on its release; B held for three seconds leaves.  A new code ends at its 10th button
or after 3 s with nothing pressed; a code being checked ends at its own length.  Given once,
the code holds until the next boot (LOCK_OPEN, WRAM)."""
import ciclone as c

CFG_LOCK = 0xFF0100 + 0x1DC
LOCK_OPEN = 0x7E940A
CODE = ("B", "Y", "SEL", "START")          # 0x1234
LOCKED = "---\nLockCode: BYsS\n"


def _row(m, label, tries=30):
    want = c.encode_menu_text(c.tr(label))
    for _ in range(tries):
        if want in m.bar_row():
            return
        m.press("DOWN")
        m.step(6)
    raise c.MenuError(f"sem a linha {want!r}\n{m.text()}")


def _main_menu(m):
    for _ in range(10):
        m.press("X")
        m.settle()
        if m.has(c.tr("mtext_mm_cfg")):
            return
    raise c.MenuError("o menu principal não abriu\n" + m.text())


def _type(m, buttons):
    for b in buttons:
        m.press(b, hold=4, after=6)
    m.settle(stable=8)


def _keypad(m):
    return m.has(c.tr("text_lock_hint"))


def test_settings_asks_for_the_code_once(t):
    m = t.menu(t.sd(config=LOCKED))
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    assert _keypad(m) and m.has(c.tr("text_lock_enter")), m.text()
    _type(m, ("B", "B", "B", "B"))
    assert m.has(c.tr("text_lock_wrong")) and _keypad(m), "um código errado passou\n" + m.text()
    _type(m, CODE)
    assert not _keypad(m), m.text()
    assert m.has(c.tr("mtext_cfg_browser")), "as Configurações não abriram\n" + m.text()
    assert m.wram(LOCK_OPEN)[0] == 1
    m.press("B")
    m.settle()
    m.press("A")                               # again: no code this time
    m.settle()
    assert not _keypad(m) and m.has(c.tr("mtext_cfg_browser")), m.text()


def test_settings_come_back_whole_from_browser_settings(t):
    """Settings and Browser Settings are both rebuilt in WRAM (the lock's row, the "Stop music
    on game info" row): the child opened from the parent must not take the parent's table.
    Coming back, Settings showed the browser's rows inside its own window (seen on HW)."""
    m = t.menu(t.sd())
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    assert m.has(c.tr("mtext_cfg_bsx")), m.text()
    _row(m, "mtext_cfg_browser")
    m.press("A")
    m.settle()
    assert m.has(c.tr("mtext_browser_sort")), "o Browser Settings não abriu\n" + m.text()
    # the two tables stay in their own room: Browser Settings below the bank $C3 scratch
    # (FM_SCR), Settings below FM_TAB (FM_TAB_CFG)
    for base, limit in ((0x7E9500, 0x7E9800), (0x7E9000, 0x7E9400)):
        end = base + 4
        while m.wram(end)[0] != 0:
            end += 23
        assert end < limit, f"a tabela em {base:06X} vai até {end:06X} (limite {limit:06X})"
    m.press("B")
    m.settle()
    txt = m.text()
    assert not m.has(c.tr("mtext_browser_sort")), "as Configurações voltaram com as linhas do navegador\n" + txt
    for label in ("mtext_cfg_time", "mtext_cfg_bsx", "mtext_cfg_browser", "mtext_lock_row", "mtext_cfg_tour"):
        assert m.has(c.tr(label)), f"falta {label} nas Configurações\n" + txt
    _row(m, "mtext_cfg_tour")                  # the rows still go where they say
    want = c.encode_menu_text(c.tr("mtext_cfg_browser"))
    for _ in range(30):
        if want in m.bar_row():
            break
        m.press("UP")
        m.step(6)
    m.press("A")
    m.settle()
    assert m.has(c.tr("mtext_browser_sort")), m.text()


def test_holding_b_cancels(t):
    m = t.menu(t.sd(config=LOCKED))
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    assert _keypad(m), m.text()
    m.press("B", hold=60, after=6)             # a second: a digit, not the way out
    m.settle(stable=8)
    assert _keypad(m), "um segundo de B já cancelou\n" + m.text()
    m.hold("B")
    m.step(200)
    m.release()
    m.settle()
    assert not _keypad(m), m.text()
    assert not m.has(c.tr("mtext_cfg_browser")), "cancelar abriu as Configurações\n" + m.text()
    assert m.wram(LOCK_OPEN)[0] == 0


def test_delete_asks_and_cancel_keeps_the_file(t):
    m = t.menu(t.sd(config=LOCKED))
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    _row(m, "text_filesel_context_delete_file")
    m.press("A")
    m.settle()
    assert _keypad(m), "excluir não pediu o código\n" + m.text()
    assert not m.has(c.tr("text_confirm_delete_file")), m.text()
    m.hold("B")
    m.step(200)
    m.release()
    m.settle()
    assert not _keypad(m) and not m.has(c.tr("text_confirm_delete_file")), m.text()
    assert m.has(c.tr("text_filesel_context_delete_file")), "o menu de contexto sumiu\n" + m.text()
    m.press("B")
    m.settle()
    assert "Test Game.sfc" in m.list_names(), m.list_names()


def test_free_rows_do_not_ask(t):
    """Copy and the game's cheat list stay free; so does everything with no code set."""
    m = t.menu(t.sd(config=LOCKED))
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_copy")
    m.press("A")
    m.settle()
    assert not _keypad(m), m.text()
    m = t.menu()
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    _row(m, "text_filesel_context_delete_file")
    m.press("A")
    m.settle()
    assert not _keypad(m) and m.has(c.tr("text_confirm_delete_file")), m.text()


def test_set_change_and_remove_the_code(t):
    m = t.menu()
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    _row(m, "mtext_lock_row")                   # right before the tour
    m.settle()
    before = m.text()
    m.press("A")
    m.settle()
    assert m.has(c.tr("text_lock_new")), m.text()
    assert m.has(c.tr("text_lock_wait")), "sem a instrução de esperar 3 s\n" + m.text()
    _type(m, CODE)
    assert m.has(c.tr("text_lock_new")), "terminou antes dos 3 s\n" + m.text()
    m.step(200)                                 # 3 s with nothing pressed: that is the code
    m.settle(stable=8)
    assert m.has(c.tr("text_lock_again")), m.text()
    _type(m, ("L", "R", "L", "R"))
    m.step(200)
    assert m.has(c.tr("text_lock_nomatch")), "códigos diferentes aceitos\n" + m.text()
    m.press("A")
    m.settle()
    assert m.psram(CFG_LOCK, 5) == bytes(5)
    m.press("A")                                # the row again: a code of 10 ends by itself
    m.settle()
    TEN = ("B", "Y", "SEL", "START", "UP", "DOWN", "LEFT", "RIGHT", "A", "X")
    _type(m, TEN)
    assert m.has(c.tr("text_lock_again")), "o 10º botão não terminou o código\n" + m.text()
    _type(m, TEN)
    assert m.has(c.tr("text_lock_on")), m.text()
    assert m.psram(CFG_LOCK, 5) == bytes.fromhex("123456789a"), m.psram(CFG_LOCK, 5).hex()
    assert m.wram(LOCK_OPEN)[0] == 0, "cadastrar deixou a sessão aberta: a trava só valeria no boot"
    m.press("A")
    m.settle()
    m.press("A")                                # now a menu: change / turn off
    m.settle()
    assert m.has(c.tr("mtext_lock_change")) and m.has(c.tr("mtext_lock_remove")), m.text()
    _row(m, "mtext_lock_remove")
    m.press("A")
    m.settle()
    assert m.has(c.tr("text_lock_off")), m.text()
    assert m.psram(CFG_LOCK, 5) == bytes(5)
    m.press("A")                                # the popup away: Settings as it was
    m.settle()
    assert m.text() == before, "as Configurações voltaram rasgadas\n" + m.text()


def test_a_code_the_menu_cannot_take_is_no_lock(t):
    """Fewer than 4 buttons (or a letter that is not one) is no code: no keypad."""
    m = t.menu(t.sd(config="---\nLockCode: BYs\n"))   # 3 buttons
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    assert not _keypad(m) and m.has(c.tr("mtext_cfg_browser")), m.text()


def _smw_locked(t):
    import test_games as tg
    m = t.menu(t.sd(config=LOCKED, extra={"/Super Mario World.sfc":
                                           c.game_rom(tg.SMW, "Super Mario World (USA)")}))
    m.goto("Super Mario World.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    mode = lambda: m.u8(tg.SMW_MODE)                    # noqa: E731
    m.wait(lambda: mode() == 0x07, frames=900, what="the title screen")
    tg._press_until(m, "START", lambda: mode() == 0x14, "the intro level")
    m.step(600)
    tg._press_until(m, "B", lambda: mode() == 0x0E, "the overworld", after=120)
    tg._press_until(m, "Y", lambda: mode() == 0x14, "Yoshi's House", after=120)
    m.step(60)
    m.hold(*m.menu_combo())
    m.step(20)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == tg.TAB_ON, frames=120, what="o menu in-game")
    return m, tg


def test_ingame_game_options_ask_for_the_code(t):
    m, tg = _smw_locked(t)
    m.press("Y", hold=6, after=60)
    m.wait(lambda: "Code (hold B" in tg._ovl_text(m), frames=120, what="o teclado no rodapé")
    assert "Game options" not in tg._ovl_text(m)
    for b in ("B", "B", "B", "B"):
        m.press(b, hold=4, after=8)
    m.wait(lambda: "Wrong code" in tg._ovl_text(m), frames=60, what="código errado")
    for b in CODE:
        m.press(b, hold=4, after=8)
    m.wait(lambda: "Game options" in tg._ovl_text(m), frames=180, what="a tela de opções do jogo")
    assert "Code (hold B" not in tg._ovl_text(m) and "Wrong code" not in tg._ovl_text(m)
    m.press("B", hold=6, after=60)                     # back to the bar: no code this time
    m.press("Y", hold=6, after=60)
    m.wait(lambda: "Game options" in tg._ovl_text(m), frames=180, what="de novo sem código")


def test_ingame_cancel_brings_the_footer_back(t):
    m, tg = _smw_locked(t)
    m.press("Y", hold=6, after=60)
    m.wait(lambda: "Code (hold B" in tg._ovl_text(m), frames=120, what="o teclado no rodapé")
    m.hold("B")
    m.step(200)
    m.release()
    m.step(30)
    text = tg._ovl_text(m)
    assert "Code (hold B" not in text and "Game options" not in text, text
    assert m.rgb(12, 10) == tg.TAB_ON, "o menu in-game fechou"


def test_game_info_l_and_r_ask_over_the_browser(t):
    """L / R on the game info card: the info screen is torn down first, or the keypad would
    be drawn where nothing shows.  Cancelled, the card comes back; the code opens the screen."""
    m = t.menu(t.sd(config=LOCKED + "ShowGameInfo: 1\n"))
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.step(40)
    m.press("R", hold=4, after=40)
    m.wait(lambda: _keypad(m), frames=180, what="o teclado sobre o navegador")
    m.hold("B")
    m.step(200)
    m.release()
    m.wait(lambda: m.u16("screen_dma_disable") == 1, frames=300, what="a ficha de volta")
    m.step(40)
    m.press("L", hold=4, after=40)
    m.wait(lambda: _keypad(m), frames=180, what="o teclado sobre o navegador")
    _type(m, CODE)
    m.wait(lambda: m.has(c.tr("mtext_cfg_ingame")), frames=300, what="as opções do jogo")


def test_a_six_button_code_is_checked_at_its_length(t):
    """Asked, the code ends at its own length (no 3 s wait), and a wrong one of the same length
    is refused; 3 s after four or more buttons a shorter attempt is checked (and is wrong)."""
    m = t.menu(t.sd(config="---\nLockCode: AXLRud\n"))
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    _type(m, ("A", "X", "L", "R"))
    m.step(200)
    m.settle(stable=8)
    assert m.has(c.tr("text_lock_wrong")) and _keypad(m), m.text()
    _type(m, ("A", "X", "L", "R", "UP", "DOWN"))
    assert not _keypad(m) and m.has(c.tr("mtext_cfg_browser")), m.text()


def test_a_dropped_report_does_not_restart_the_hold(t):
    """A wireless pad drops a report now and then: B held with a one-frame gap every 30 frames
    still cancels at about 3 s, and types no B (a release is real after 4 frames up)."""
    m = t.menu(t.sd(config=LOCKED))
    _main_menu(m)
    _row(m, "mtext_mm_cfg")
    m.press("A")
    m.settle()
    assert _keypad(m), m.text()
    frames = 0
    while _keypad(m) and frames < 400:
        m.hold("B")
        m.step(29)
        m.release()
        m.step(1)
        frames += 30
        assert "*" not in m.text().split(c.tr("text_lock_enter"))[-1].split(c.tr("text_lock_hint"))[0], \
            "um soluço do controle digitou um B\n" + m.text()
    assert not _keypad(m) and frames <= 240, (frames, m.text())
