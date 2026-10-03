"""Carga dos outros consoles e chips que o firmware estagia na PSRAM antes do boot: NES, Master
System, Atari 2600, Game Boy (SGB), Sufami Turbo e SPC7110 com RTC.

O modelo do FPGA não roda esses cores (trocar de core só reinicia o estado dele), então o que se
testa é a parte do FIRMWARE: a detecção, o pré-check dos arquivos de suporte (faltando = popup e
o menu segue vivo), o estágio da imagem na PSRAM e a entrada no laço do jogo. Core, player e BIOS
entram no cartão como arquivos FALSOS: o firmware só confere que existem e os copia."""
import sys

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
from sd_fixtures import lorom  # noqa: E402

PLAYER = lorom("CICLONE PLAYER")     # SNES-side player/BIOS falso: um laço infinito que boota
CORE = b"\0" * 1024                  # o modelo não lê o bitstream

PRG = bytes((i * 7 + 3) & 0xFF for i in range(16384))
CHR = bytes((i * 13 + 5) & 0xFF for i in range(8192))
NES = b"NES\x1a" + bytes([1, 1, 0, 0]) + bytes(8) + PRG + CHR          # NROM 16K + 8K
SMS = bytes((i * 11 + 1) & 0xFF for i in range(32768))
A26 = bytes((i * 5 + 9) & 0xFF for i in range(4096))


def _gb() -> bytes:
    rom = bytearray((i * 3) & 0xFF for i in range(32768))
    rom[0x134:0x144] = b"CICLONE GB".ljust(16, b"\0")
    rom[0x143] = 0x00                  # DMG
    rom[0x146] = 0x03                  # SGB functions
    rom[0x147] = 0x00                  # ROM only
    rom[0x148] = 0x00                  # 32 KB
    rom[0x149] = 0x00
    rom[0x14B] = 0x33
    return bytes(rom)


def _load(t, sd, name):
    m = t.menu(sd)
    m.goto(name)
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")                                   # Jogar
    return m


def _warned(m):
    """Core experimental: depois do pré-check o firmware pergunta e o menu mostra o aviso, com
    o título (os '*' do rótulo só marcam a palavra verde), as linhas do texto e as 3 opções;
    Iniciar vem com a barra."""
    m.wait_text(c.tr("text_exp_l1"), frames=1800)
    title = c.tr("text_exp_title").replace("*", "")
    assert m.has(title), m.text()
    for label in ("text_exp_l2", "text_exp_l4", "text_exp_l5", "text_exp_start", "text_exp_back",
                  "text_exp_nowarn"):
        assert m.has(c.tr(label)), (label, m.text())
    assert "experimental core: asking the menu" in m.fwlog()


def _booted(m, experimental=True):
    if experimental:
        _warned(m)
        m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot")


def _refused(m, missing):
    """Pré-check: o popup cita o arquivo que falta e o menu continua (sem boot). O aviso de core
    experimental só vem depois de TODO o pré-check, então um arquivo faltando nunca o mostra."""
    m.wait_text(missing, frames=1200)
    assert "going to snes main loop" not in m.fwlog()
    assert "experimental core: asking" not in m.fwlog()
    m.press("B")
    m.settle()
    m.close()


def test_nes_stages_prg_and_chr(t):
    sd = t.sd(extra={"/Game.nes": NES, "/sd2snes/fpga_nes.bi3": CORE, "/sd2snes/nes_snes.bin": PLAYER})
    m = _load(t, sd, "Game.nes")
    _booted(m)
    assert m.psram(0x000000, 64) == PRG[:64], m.fwlog()[-2000:]      # NES_PSRAM_PRG_ADDR
    assert m.psram(0x200000, 64) == CHR[:64]                          # NES_PSRAM_CHR_ADDR
    m.close()


def test_experimental_warning_back_returns_to_the_browser(t):
    """B no aviso: nada boota, o firmware recusa a carga sem popup de erro e o navegador volta."""
    sd = t.sd(extra={"/Game.sms": SMS, "/sd2snes/fpga_sms.bi3": CORE, "/sd2snes/sms_snes.bin": PLAYER})
    m = _load(t, sd, "Game.sms")
    _warned(m)
    m.press("B")
    m.wait(lambda: "experimental core: answer 2" in m.fwlog(), frames=600, what="a resposta")
    m.wait(lambda: m.has("Game.sms") and not m.has(c.tr("text_exp_l1")), frames=600, what="o navegador")
    m.step(120)
    assert "going to snes main loop" not in m.fwlog()
    assert not m.has(c.tr("text_err_generic"))
    assert m.psram(0xFF07E6, 1) == b"\x00", "the question is still up"
    m.close()


def test_experimental_warning_back_option(t):
    """A opção Voltar (a do meio) faz o mesmo que o B."""
    sd = t.sd(extra={"/Game.sms": SMS, "/sd2snes/fpga_sms.bi3": CORE, "/sd2snes/sms_snes.bin": PLAYER})
    m = _load(t, sd, "Game.sms")
    _warned(m)
    m.press("DOWN")
    m.step(10)
    m.press("A")
    m.wait(lambda: "experimental core: answer 2" in m.fwlog(), frames=600, what="a resposta")
    m.wait(lambda: m.has("Game.sms") and not m.has(c.tr("text_exp_l1")), frames=600, what="o navegador")
    assert "going to snes main loop" not in m.fwlog()
    m.close()


def test_experimental_warning_dont_warn_again(t):
    """A terceira opção inicia o jogo e grava WarnExperimental: false no config.yml."""
    sd = t.sd(extra={"/Game.nes": NES, "/sd2snes/fpga_nes.bi3": CORE, "/sd2snes/nes_snes.bin": PLAYER})
    m = _load(t, sd, "Game.nes")
    _warned(m)
    m.press("DOWN")
    m.step(10)
    m.press("DOWN")
    m.step(10)
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot")
    assert "experimental core: answer 3" in m.fwlog()
    m.close()
    cfg = t.read(sd, "/sd2snes/config.yml").decode()
    assert "WarnExperimental: false" in cfg, cfg


def test_experimental_warning_off_starts_directly(t):
    """Com WarnExperimental desligado o firmware nem pergunta."""
    sd = t.sd(config="---\nWarnExperimental: false\n",
              extra={"/Game.nes": NES, "/sd2snes/fpga_nes.bi3": CORE, "/sd2snes/nes_snes.bin": PLAYER})
    m = _load(t, sd, "Game.nes")
    _booted(m, experimental=False)
    assert "experimental core: asking" not in m.fwlog()
    m.close()


def test_nes_without_the_player_is_refused(t):
    m = _load(t, t.sd(extra={"/Game.nes": NES, "/sd2snes/fpga_nes.bi3": CORE}), "Game.nes")
    _refused(m, "nes_snes.bin")


def test_sms_stages_the_rom(t):
    sd = t.sd(extra={"/Game.sms": SMS, "/sd2snes/fpga_sms.bi3": CORE, "/sd2snes/sms_snes.bin": PLAYER})
    m = _load(t, sd, "Game.sms")
    _booted(m)
    assert m.psram(0x300000, 64) == SMS[:64], m.fwlog()[-2000:]      # SMS_ROM_PSRAM
    m.close()


def test_sms_without_the_player_is_refused(t):
    m = _load(t, t.sd(extra={"/Game.sms": SMS, "/sd2snes/fpga_sms.bi3": CORE}), "Game.sms")
    _refused(m, "sms_snes.bin")


def test_a26_detects_and_stages(t):
    sd = t.sd(extra={"/Game.a26": A26, "/sd2snes/fpga_a26.bi3": CORE, "/sd2snes/a26_snes.bin": PLAYER})
    m = _load(t, sd, "Game.a26")
    _booted(m)
    assert "A26: 4096 B scheme=" in m.fwlog(), m.fwlog()[-2000:]
    assert m.psram(0x300000, 64) == A26[:64]                          # A26_ROM_PSRAM
    m.close()


def test_a26_without_the_player_is_refused(t):
    m = _load(t, t.sd(extra={"/Game.a26": A26, "/sd2snes/fpga_a26.bi3": CORE}), "Game.a26")
    _refused(m, "a26_snes.bin")


def test_gb_boots_on_the_sgb(t):
    sd = t.sd(extra={"/Game.gb": _gb(), "/sd2snes/fpga_sgb.bi3": CORE,
                     "/sd2snes/sgb2_boot.bin": bytes(256), "/sd2snes/sgb2_snes.bin": PLAYER})
    m = _load(t, sd, "Game.gb")
    _booted(m, experimental=False)                 # the Super Game Boy is not experimental
    assert "attempting to load SGB boot ROM /sd2snes/sgb2_boot.bin" in m.fwlog(), m.fwlog()[-2000:]
    m.close()


def test_gb_without_the_sgb_bios_is_refused(t):
    m = _load(t, t.sd(extra={"/Game.gb": _gb(), "/sd2snes/fpga_sgb.bi3": CORE}), "Game.gb")
    _refused(m, "sgb2_snes.bin")


def _st(title: str) -> bytes:
    rom = bytearray((i * 17 + 2) & 0xFF for i in range(0x20000))      # 128 KB minicart
    rom[0:14] = b"BANDAI SFC-ADX"
    rom[0x10:0x10 + 14] = title.encode().ljust(14)[:14]
    return bytes(rom)


def test_sufami_turbo_with_slot_b(t):
    """.st: o diálogo de patches vira o seletor do Slot B; a BIOS vai para o início da PSRAM,
    o Slot A e o Slot B para as janelas deles."""
    a, b = _st("CICLONE A"), _st("CICLONE B")
    sd = t.sd(extra={"/ST/Alpha.st": a, "/ST/Beta.st": b, "/sd2snes/stbios.bin": PLAYER})
    m = t.menu(sd)
    m.goto("ST/")
    m.press("A")
    m.wait(lambda: m.has("Alpha.st"), what="a pasta")
    m.settle()
    m.goto("Alpha.st")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")                                   # Jogar -> seletor do Slot B
    m.wait_text("Beta")
    m.settle()
    for _ in range(4):
        if "Beta" in m.bar_row():
            break
        m.press("DOWN")
        m.step(10)
    assert "Beta" in m.bar_row(), m.text()
    m.press("A")
    _booted(m, experimental=False)
    assert m.psram(0x000000, 64) == PLAYER[:64]                       # SUFAMI_SLOTA_BIOS_ADDR
    assert m.psram(0x100000, 64) == a[:64]                            # SUFAMI_SLOTA_ROM_ADDR
    assert m.psram(0x700000, 64) == b[:64], m.fwlog()[-2000:]         # SUFAMI_SLOTB_ROM_ADDR
    m.close()


def test_sufami_turbo_without_the_bios_is_refused(t):
    sd = t.sd(extra={"/Alpha.st": _st("CICLONE A")})
    m = t.menu(sd)
    m.goto("Alpha.st")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")
    m.wait_text("Alpha", frames=600)                # o seletor do Slot B (só com o próprio jogo)
    m.settle()
    m.press("A")                                   # sem Slot B
    _refused(m, "stbios.bin")


def _spc7110(chipset: int) -> bytes:
    """HiROM de 2 MB com o header do SPC7110 ($FFD5 = $3A, $FFD6 = $F5/$F9 com RTC)."""
    import struct
    rom = bytearray(b"\xff" * 0x200000)
    rom[0:3] = b"\x80\xfe\xea"
    h = 0xFFC0
    rom[h:h + 21] = b"CICLONE SPC7110".ljust(21)
    rom[h + 0x15] = 0x3A
    rom[h + 0x16] = chipset
    rom[h + 0x17] = 0x0B                          # 2 MB
    rom[h + 0x18] = 0x03                          # 8 KB SRAM
    rom[h + 0x19] = 0x00
    rom[h + 0x1A] = 0x33
    rom[0xFFFC:0xFFFE] = struct.pack("<H", 0x8000)
    rom[0x8000:0x8003] = b"\x80\xfe\xea"
    s = sum(rom) & 0xFFFF
    rom[h + 0x1C:h + 0x1E] = struct.pack("<H", s ^ 0xFFFF)
    rom[h + 0x1E:h + 0x20] = struct.pack("<H", s)
    return bytes(rom)


def test_spc7110_with_rtc(t):
    """Chip $F9: core SPC7110 com o RTC. O modelo não tem a bateria virtual, e o firmware cai
    no relógio do console -- o caminho que um core sem a bateria pega."""
    sd = t.sd(extra={"/Rtc.sfc": _spc7110(0xF9), "/sd2snes/fpga_spc7110.bi3": CORE})
    m = _load(t, sd, "Rtc.sfc")
    _booted(m, experimental=False)
    assert "SPC7110 RTC:" in m.fwlog(), m.fwlog()[-2000:]
    m.close()


def test_spc7110_without_the_core_is_refused(t):
    m = _load(t, t.sd(extra={"/Rtc.sfc": _spc7110(0xF9)}), "Rtc.sfc")
    _refused(m, "fpga_spc7110")


def _cgb_boot() -> bytes:
    """O boot ROM CGB do SameBoy (MIT) em roms/ -- o firmware confere o CRC32 dele."""
    import zlib
    for f in sorted((c.ROOT / "roms").rglob("*.bin")):
        d = f.read_bytes()
        if len(d) == 2304 and zlib.crc32(d) == 0x8113B4D8:
            return d
    raise c.Skip("cgb_boot.bin (SameBoy, CRC32 8113b4d8) not found under roms/")


def _gbc() -> bytes:
    rom = bytearray(_gb())
    rom[0x143] = 0xC0                              # CGB only
    return bytes(rom)


def test_gbc_routes_to_the_gbc_core(t):
    sd = t.sd(extra={"/Game.gbc": _gbc(), "/sd2snes/fpga_gbc.bi3": CORE,
                     "/sd2snes/gbc_snes.bin": PLAYER, "/sd2snes/cgb_boot.bin": _cgb_boot()})
    m = _load(t, sd, "Game.gbc")
    _booted(m)
    assert "fpga_gbc.bi3" in m.fwlog(), m.fwlog()[-2000:]
    m.close()


def test_gbc_without_the_player_is_refused(t):
    m = _load(t, t.sd(extra={"/Game.gbc": _gbc(), "/sd2snes/fpga_gbc.bi3": CORE}), "Game.gbc")
    _refused(m, "gbc_snes.bin")
