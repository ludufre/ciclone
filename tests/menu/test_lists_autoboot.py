"""Jogar a partir de Recentes e Favoritos, e o autoboot (definir pelo menu de contexto e subir
direto no jogo no boot seguinte). As listas no cartao sao entradas terminadas em NUL, como o
cfg.c as grava."""
import ciclone as c

LISTS = {
    "/sd2snes/lastgame.cfg": b"/MSU Game/msugame.sfc\0/Test Game.sfc\0",
    "/sd2snes/favorites.cfg": b"/Two Games/second.sfc\0",
}


def _booted(m, path):
    """A firmware abriu `path` e entrou no laco do jogo."""
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot da ROM")
    assert f"file_open ({path}, 01): FR_OK" in m.fwlog(), m.fwlog()[-2000:]


def _play_from_ficha(m, title):
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has(title), what="a ficha")
    m.settle()
    m.press("A")                                   # Jogar


def test_play_from_recents(t):
    """START (Recentes) -> 2a linha -> A (ficha) -> A: a ROM da linha boota, e a lista de
    Recentes a coloca no topo."""
    sd = t.sd(extra=LISTS)
    m = t.menu(sd)
    m.press("START")
    m.wait_text(c.tr("text_last"))
    m.press("DOWN")
    m.step(10)
    m.press("A")
    _play_from_ficha(m, "Test Game")
    _booted(m, "/Test Game.sfc")
    m.close()
    rec = t.read(sd, "/sd2snes/lastgame.cfg")
    assert rec.startswith(b"/Test Game.sfc"), rec


def test_play_from_favorites(t):
    sd = t.sd(extra=LISTS)
    m = t.menu(sd)
    m.press("SEL")
    m.wait_text(c.tr("text_favorite"))
    m.press("A")
    _play_from_ficha(m, "second")
    _booted(m, "/Two Games/second.sfc")
    m.close()
    rec = t.read(sd, "/sd2snes/lastgame.cfg")
    assert rec.startswith(b"/Two Games/second.sfc"), rec


def test_set_autoboot_from_context(t):
    """Y na ROM -> "Definir como autoboot" grava /sd2snes/autoboot.cfg com o caminho completo."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    row = c.tr("text_filesel_set_as_autoboot")
    for _ in range(6):
        if row in m.bar_row():
            break
        m.press("DOWN")
        m.step(10)
    assert row in m.bar_row(), m.text()
    m.press("A")
    m.settle()
    m.close()
    assert t.read(sd, "/sd2snes/autoboot.cfg") == b"/Test Game.sfc\0"


def _cold_boot(t, sd):
    """Sobe o console sem esperar o browser (o autoboot nunca o mostra)."""
    m = c.Menu(sd, t.dir / f"run{len(t.menus) + 1}")
    t.menus.append(m)
    return m


def test_autoboot_boots_the_game(t):
    sd = t.sd(extra={"/sd2snes/autoboot.cfg": b"/Two Games/second.sfc\0"})
    m = _cold_boot(t, sd)
    _booted(m, "/Two Games/second.sfc")
    assert "Autobooting: /Two Games/second.sfc" in m.fwlog()
    m.close()
