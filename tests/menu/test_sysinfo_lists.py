"""System Information (a tela que o menu monta a partir do bloco SI2 que a firmware publica),
"Excluir save" pelo menu de contexto e tirar um jogo de Favoritos e de Recentes pelo menu de
contexto das listas."""
import ciclone as c

SI2 = 0xFF1200                    # SYSINFO_BLK: magic 'S','I' + versão
LISTS = {
    "/sd2snes/lastgame.cfg": b"/MSU Game/msugame.sfc\0/Test Game.sfc\0",
    "/sd2snes/favorites.cfg": b"/Two Games/second.sfc\0/Test Game.sfc\0",
}


def _row(m, label, tries=10):
    want = c.tr(label)
    for _ in range(tries):
        if want in m.bar_row():
            return
        m.press("DOWN")
        m.step(8)
    raise c.MenuError(f"{label} não está no menu\n{m.text()}")


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


def test_system_information(t):
    m = t.menu()
    m.press("X")
    m.settle()
    _row(m, "mtext_mm_sysinfo")
    m.press("A")
    m.wait_text("Firmware version:")
    m.wait_text("Card usage:", frames=1800)        # o f_getfree termina e as linhas do cartão entram
    assert m.psram(SI2, 2) == b"SI", m.psram(SI2, 4)
    line = next(r for r in m.screen() if "Firmware version:" in r)
    assert "ciclone-host" in line, line           # a versão do build do host, vinda do bloco SI2
    m.press("B")
    m.wait_gone("Firmware version:")
    m.settle()
    m.close()


def test_delete_save_file(t):
    sd = t.sd(extra={"/sd2snes/saves/TE/Test Game.srm": b"\x5a" * 2048})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    _row(m, "text_filesel_context_delete_srm")
    m.press("A")
    _confirm_yes(m)
    m.close()
    assert "Test Game.srm" not in t.listdir(sd, "/sd2snes/saves/TE")
    assert "Test Game.sfc" in t.listdir(sd, "/")   # a ROM fica


def test_remove_from_favorites(t):
    sd = t.sd(extra=LISTS)
    m = t.menu(sd)
    m.press("SEL")
    m.wait_text(c.tr("text_favorite"))
    m.press("DOWN")                                # Test Game
    m.step(10)
    m.press("Y")
    m.settle()
    _row(m, "text_filesel_context_remove_from_favorites")
    m.press("A")
    m.settle()
    assert not m.has("Test Game.sfc"), m.text()
    m.close()
    fav = t.read(sd, "/sd2snes/favorites.cfg")
    assert b"Test Game" not in fav and b"second.sfc" in fav, fav


def test_remove_from_recents(t):
    sd = t.sd(extra=LISTS)
    m = t.menu(sd)
    m.press("START")
    m.wait_text(c.tr("text_last"))
    m.press("Y")                                   # a 1a linha: msugame
    m.settle()
    _row(m, "text_recent_context_remove_from_recent")
    m.press("A")
    m.settle()
    assert not m.has("msugame.sfc"), m.text()
    m.close()
    rec = t.read(sd, "/sd2snes/lastgame.cfg")
    assert b"msugame" not in rec and b"Test Game.sfc" in rec, rec
