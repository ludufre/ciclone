"""Carga de jogo pelo caminho real (ficha -> A -> game_handshake -> firmware)."""
import sys

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
import sd_fixtures as fx  # noqa: E402

GSU_ROM = fx.lorom("SUPERFX TEST", chipset=0x13)    # Super FX: exige fpga_gsu.bi3, que o cartão não tem


def test_missing_chip_core_is_refused_with_popup(t):
    """ROM de chip sem o core FPGA no cartão: o pré-check da firmware NACKa antes de bootar, o
    menu mostra o popup com o arquivo que falta e volta ao browser vivo (sem reset)."""
    m = t.menu(t.sd(extra={"/SuperFX Game.sfc": GSU_ROM}))
    m.goto("SuperFX Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("SuperFX Game"), what="a ficha")
    m.press("A")                                        # Play
    m.wait_text(c.tr("text_err_supplfile"), frames=600)
    assert m.has("fpga_gsu.bi3"), m.text()
    assert m.psram(0xFF071D, 1) == b"\x01"               # LOAD_NACK
    assert "missing=fpga_gsu.bi3" in m.fwlog()
    m.press("A")                                        # fecha o popup
    m.wait_gone(c.tr("text_err_supplfile"))
    m.settle()
    assert m.selected() == "SuperFX Game.sfc"
    assert "SuperFX Game.sfc" in m.list_names()
    assert m.u16("screen_dma_disable") == 0


def test_boot_rom_records_recent(t):
    """ROM comum: carrega, a firmware entra no laço do jogo e grava a entrada em Recentes."""
    sd = t.sd()
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=900, what="o boot da ROM")
    assert "loaded 131072 bytes" in m.fwlog()
    m.close()
    rec = t.read(sd, "/sd2snes/lastgame.cfg")
    assert rec is not None and rec.startswith(b"/Test Game.sfc"), rec


LISTS = {
    "/sd2snes/lastgame.cfg": b"/Test Game.sfc\n/MSU Game/msugame.sfc\n",
    "/sd2snes/favorites.cfg": b"/Two Games/second.sfc\n",
}


def test_favorites_list_on_select(t):
    m = t.menu(t.sd(extra=LISTS))
    m.press("SEL")
    m.wait_text(c.tr("text_favorite"))
    assert m.has("second.sfc"), m.text()
    m.press("B")
    m.wait_gone(c.tr("text_favorite"))
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF


def test_recents_list_on_start(t):
    m = t.menu(t.sd(extra=LISTS))
    m.press("START")
    m.wait_text(c.tr("text_last"))
    rows = m.screen()
    top = m.row_of(c.tr("text_last"))
    assert "Test Game.sfc" in rows[top + 1] and "msugame.sfc" in rows[top + 2], "\n".join(rows)
    m.press("B")
    m.wait_gone(c.tr("text_last"))
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF
