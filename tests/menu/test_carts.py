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


def test_st018_without_its_core_is_refused(t):
    rom = lorom("CICLONE ST018", chipset=0xF5, mapmode=0x30)
    sd = t.sd(extra={"/Shogi 2.sfc": rom, "/sd2snes/st018.rom": b"\0" * 163840})
    _refused(_load(t, sd, "Shogi 2.sfc"), "fpga_st0018.bi3")


def test_20_in_1_multicart_is_detected_by_its_bank_6_header(t):
    """1 MB sem cabeçalho válido no banco 0: o firmware reconhece o cartucho pelo cabeçalho do
    banco 6 e pede o core dele (ausente no cartão = popup com o nome do arquivo)."""
    rom = bytearray(b"\xff" * 0x100000)
    rom[0x37FC0:0x37FE0] = HDR_BANK6
    _refused(_load(t, t.sd(extra={"/Multi.sfc": bytes(rom)}), "Multi.sfc"), "fpga_col20.bi3")


# --- cartucho com coprocessador RP2040 (core xc): a ROM SNES é só o kernel; o firmware monta a
# imagem do soft CPU a partir do dump do flash do RP2040 e do xc_soc.bin.  O modelo do FPGA não
# roda o soft CPU: o que se testa é a recusa no pré-check e o layout que o firmware deixa na PSRAM.
def _xc_src(name):
    import re
    src = (c.SD2SNES / "src" / "xc.c").read_text()
    return re.search(r'#define %s\s+"([^"]+)"' % name, src).group(1)


def _xc_rom():
    rom = bytearray(lorom("CICLONE XC", chipset=0x63, mapmode=0x30))
    rom[0x7FB0:0x7FB6] = b"BMXCRI"                 # maker + game code que o smc.c exige
    return bytes(rom)


def _xc_dump(size=0x1000000):
    """Flash de 16 MB com a assinatura que o firmware confere (0x4905 em multicore_launch_core1,
    flash 0x59060) e um padrão por banco de 64 KB, para achar cada pedaço na PSRAM."""
    d = bytearray(size)
    for b in range(size >> 16):
        d[b << 16:(b << 16) + 4] = struct.pack("<I", 0xA5000000 | b)
    if size > 0x59062:
        d[0x59060:0x59062] = struct.pack("<H", 0x4905)
    d[0xFF8000:0xFF8010] = b"SAVE FROM DUMP!!"
    return bytes(d)


def _xc_soc(mk2p=True):
    """xc_soc.bin mínimo: cabeçalho XSOC v1, bootrom e adições (16 KB cada) e a tabela de patches
    com um patch "return 0" (tipo 2) em flash 0x10001000, mais a tabela MK2P vazia."""
    b = bytearray(b"\xff" * (0x200 + 0x8000))
    struct.pack_into("<II", b, 0, 0x434F5358, 1)
    b[0x200:0x210] = b"BOOTROM BOOTROM!"
    struct.pack_into("<IIII", b, 0x4200, 0x5843584D, 2, 0, 1)
    struct.pack_into("<III", b, 0x4210, 0x10001000, 0, 2)
    if mk2p:
        struct.pack_into("<II", b, 0x421C, 0x50324B4D, 0)
    return bytes(b)


XC_CORE = "/sd2snes/fpga_xc.bi3"


def _xc_card(t, **files):
    extra = {"/Soft CPU.sfc": _xc_rom()}
    extra.update({k: v for k, v in files.items() if v is not None})
    return t.sd(extra=extra, size_mb=64)


def test_xc_without_its_core_is_refused(t):
    _refused(_load(t, _xc_card(t), "Soft CPU.sfc"), "fpga_xc.bi3")


def test_xc_without_the_flash_dump_is_refused(t):
    sd = _xc_card(t, **{XC_CORE: CORE, _xc_src("XC_SOC_FILE"): _xc_soc()})
    dump = _xc_src("XC_FLASH_FILE").rsplit("/", 1)[1]
    _refused(_load(t, sd, "Soft CPU.sfc"), dump)


def test_xc_with_a_short_flash_dump_is_refused(t):
    sd = _xc_card(t, **{XC_CORE: CORE, _xc_src("XC_SOC_FILE"): _xc_soc(),
                        _xc_src("XC_FLASH_FILE"): _xc_dump(0x800000)})
    dump = _xc_src("XC_FLASH_FILE").rsplit("/", 1)[1]
    _refused(_load(t, sd, "Soft CPU.sfc"), dump)


def test_xc_with_a_foreign_support_file_is_refused(t):
    bad = bytearray(_xc_soc())
    struct.pack_into("<I", bad, 4, 2)              # outra versão do cabeçalho
    sd = _xc_card(t, **{XC_CORE: CORE, _xc_src("XC_FLASH_FILE"): _xc_dump(),
                        _xc_src("XC_SOC_FILE"): bytes(bad)})
    _refused(_load(t, sd, "Soft CPU.sfc"), "xc_soc.bin")


def test_xc_boots_with_the_soft_cpu_image_in_psram(t):
    """Layout da imagem (src/xc.c): kernel em 0, flash 0x020000+ no mesmo endereço, os primeiros
    128 KB do flash em 0xD00000, bootrom em 0xD20000, patch aplicado e o save inicial vindo do
    dump.  E nada do que o init() estaga para os outros jogos (menu in-game em 0xC80000, registros
    de cheat em 0xD00000) pode cair por cima da imagem."""
    dump = _xc_dump()
    sd = _xc_card(t, **{XC_CORE: CORE, _xc_src("XC_FLASH_FILE"): dump,
                        _xc_src("XC_SOC_FILE"): _xc_soc(),
                        "/sd2snes/cheats/SO/Soft CPU.yml":
                            b"---\r\n- Name: \"x\"\r\n  Enabled: true\r\n  Code:\r\n  - 7E0000FF\r\n"})
    m = _load(t, sd, "Soft CPU.sfc")
    _booted(m)
    log = m.fwlog()
    assert "XC: image ok, 1+0 patches" in log, log[-2000:]
    assert m.psram(0x000000, 64) == _xc_rom()[:64]
    for a in (0x020000, 0x590000, 0xC80000, 0xCF0000):
        assert m.psram(a, 4) == dump[a:a + 4], hex(a)
    assert m.psram(0xD00000, 4) == dump[0:4]
    assert m.psram(0xD10000, 4) == dump[0x10000:0x10004]
    assert m.psram(0xD20000, 16) == b"BOOTROM BOOTROM!"
    assert m.psram(0xD01000, 4) == bytes.fromhex("00207047")   # movs r0,#0; bx lr
    assert m.psram(0xE00000, 16) == b"SAVE FROM DUMP!!"
    m.close()
