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


def test_boot_hands_over_a_clean_ppu(t):
    """Toda carga, com ou sem patch: o jogo recebe VRAM, CGRAM e OAM zeradas. O reset do boot
    preserva a PPU, e um romhack que liga uma camada sem escrever o tilemap dela mostraria as
    sobras do menu (num emulador a VRAM nasce zerada e o defeito não aparece)."""
    m = t.menu(t.sd())
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=900, what="o boot da ROM")
    m.step(30)                                          # a ROM de teste é só um laço: não toca a PPU
    for space, n in (("vram", 0x10000), ("cgram", 0x200), ("oam", 0x220)):
        mem = m.peek(space, 0, n)
        dirty = sum(1 for b in mem if b)
        assert dirty == 0, f"{space}: {dirty} bytes não zerados"



def test_header_rom_size_larger_than_the_file_still_boots(t):
    """Um cabeçalho que declara mais ROM do que o arquivo tem (uma ROM de 128 KB dizendo 8 MB)
    não pode decidir o mapeamento: no LoROM uma máscara acima de 4 MB leva os bancos $00-$7F
    para a metade de cima, onde nada foi carregado, e o vetor de reset cai no vazio. O console
    real só enxerga os chips, então a máscara segue o tamanho do arquivo."""
    rom = bytearray(fx.lorom("CICLONE BIG HEADER"))
    rom[0x7FD7] = 0x0D                                  # 8 MB no cabeçalho
    m = t.menu(t.sd(extra={"/Big Header.sfc": bytes(rom)}))
    m.goto("Big Header.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=900, what="o boot da ROM")
    m.step(30)
    assert "rommask=1ffff" in m.fwlog()
    pc = m.cpu()[0] & 0x7FFFFF                          # a ROM é um "bra *" em $00:8000
    assert 0x8000 <= pc < 0x8003, hex(m.cpu()[0])

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
