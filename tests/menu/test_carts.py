"""Cartuchos que o firmware reconhece fora do caminho comum: container SFROM, os chips Seta
ST011/ST018 e o multicart de 20 jogos. Como em test_consoles, o modelo do FPGA não roda esses
cores: o que se testa é o FIRMWARE (browser, detecção, pré-check dos arquivos, carga)."""
import struct
import sys

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
from sd_fixtures import lorom  # noqa: E402

CORE = b"\0" * 1024                  # o modelo não lê o bitstream
# os 32 bytes do cabeçalho do banco 6 que o firmware compara (smc.c)
HDR_BANK6 = bytes.fromhex("5370617274616e205820536663202020"
                          "2020202020000008000d0101ffff0000")
PLAYER = lorom("CICLONE PLAYER")
GAME = lorom("CICLONE SFROM")


def _sfrom(rom: bytes, hdr_len: int = 0x30) -> bytes:
    """Container mínimo: magic, tamanho total, offset da ROM, offset do rodapé; o rodapé leva o
    tamanho da ROM a partir do 2o byte."""
    footer = hdr_len + len(rom)
    total = footer + 0x30
    hdr = bytearray(hdr_len)
    struct.pack_into("<III", hdr, 0, 0x00000100, total, hdr_len)
    struct.pack_into("<I", hdr, 0x14, footer)
    return bytes(hdr) + rom + b"\0" + struct.pack("<I", len(rom)) + bytes(0x30 - 5)


def _load(t, sd, name):
    m = t.menu(sd)
    m.goto(name)
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")                                   # Jogar
    return m


def _booted(m):
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot")


def _refused(m, missing):
    m.wait_text(missing, frames=1200)
    assert "going to snes main loop" not in m.fwlog()
    m.press("B")
    m.settle()
    m.close()


def test_sfrom_is_listed_and_boots_the_embedded_rom(t):
    """A extensão tem 5 letras (o alias 8.3 guarda 3): o browser lista pelo nome longo, e a carga
    pega a imagem de dentro do container, no offset e com o tamanho que o cabeçalho diz."""
    sd = t.sd(extra={"/Boxed Game.sfrom": _sfrom(GAME)})
    m = t.menu(sd)
    assert "Boxed Game.sfrom" in m.list_names(), m.list_names()
    m.goto("Boxed Game.sfrom")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")
    _booted(m)
    assert "SFROM: rom offset=30 size=20000" in m.fwlog(), m.fwlog()[-2000:]
    assert "loaded 131072 bytes" in m.fwlog(), m.fwlog()[-2000:]
    assert m.psram(0x000000, 64) == GAME[:64]
    m.close()
    assert t.read(sd, "/sd2snes/lastgame.cfg").startswith(b"/Boxed Game.sfrom")


def test_sfrom_with_a_broken_header_is_refused(t):
    bad = b"\xff" * 0x30 + GAME
    m = _load(t, t.sd(extra={"/Broken.sfrom": bad}), "Broken.sfrom")
    _refused(m, "Broken.sfrom")


def test_console_rom_larger_than_its_player_keeps_the_player_size(t):
    """A imagem do console (512 KB) é maior que o player SNES (128 KB) que de fato boota: a
    máscara de ROM tem que sair do player, não do arquivo que o usuário escolheu."""
    big = bytes((i * 11 + 1) & 0xFF for i in range(512 * 1024))
    sd = t.sd(extra={"/Big.sms": big, "/sd2snes/fpga_sms.bi3": CORE, "/sd2snes/sms_snes.bin": PLAYER})
    m = _load(t, sd, "Big.sms")
    m.wait_text(c.tr("text_exp_l1"), frames=1800)      # experimental core: confirm first
    m.press("A")
    _booted(m)
    assert "rommask=1ffff" in m.fwlog(), m.fwlog()[-2000:]
    m.close()


def test_st011_without_the_chip_firmware_is_refused(t):
    rom = lorom("CICLONE ST011", chipset=0xF6, mapmode=0x30)
    sd = t.sd(extra={"/Shogi.sfc": rom, "/sd2snes/fpga_st0011.bi3": CORE})
    _refused(_load(t, sd, "Shogi.sfc"), "st011.rom")


def test_st011_without_its_core_is_refused(t):
    rom = lorom("CICLONE ST011", chipset=0xF6, mapmode=0x30)
    _refused(_load(t, t.sd(extra={"/Shogi.sfc": rom}), "Shogi.sfc"), "fpga_st0011.bi3")


def test_st018_without_the_chip_firmware_is_refused(t):
    rom = lorom("CICLONE ST018", chipset=0xF5, mapmode=0x30)
    sd = t.sd(extra={"/Shogi 2.sfc": rom, "/sd2snes/fpga_st0018.bi3": CORE})
    _refused(_load(t, sd, "Shogi 2.sfc"), "st018.rom")


def test_20_in_1_multicart_is_detected_by_its_bank_6_header(t):
    """1 MB sem cabeçalho válido no banco 0: o firmware reconhece o cartucho pelo cabeçalho do
    banco 6 e pede o core dele (ausente no cartão = popup com o nome do arquivo)."""
    rom = bytearray(b"\xff" * 0x100000)
    rom[0x37FC0:0x37FE0] = HDR_BANK6
    _refused(_load(t, t.sd(extra={"/Multi.sfc": bytes(rom)}), "Multi.sfc"), "fpga_col20.bi3")
