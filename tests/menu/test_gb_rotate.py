"""GbRotateButtons (CFG +$1DA): SNES B joga como o A do Game Boy e o Y fica sozinho no B, nos dois
cores de Game Boy. O modelo do FPGA não roda nenhum dos dois, então o que se testa é o lado do
FIRMWARE e do menu:

  * a linha "Rotate Game Boy buttons" nas Opções SGB grava a chave no config.yml;
  * GBC: o firmware escreve o byte +6 do bloco "GBCF" (versão >= 2) da imagem do player já
    estagiada na PSRAM ($880000 + $7F80), e não toca num bloco versão 1;
  * SGB: o firmware troca por NOPs os 5 bytes do teste de layout na rotina de pad da BIOS
    (offset $3CDE, $3CE1 na v1.0), conferida por CRC32, e deixa intacta uma BIOS que não conhece.

O caminho do pad rodando (player GBC) está no teste de host do _repo (run_gbc_player.sh, bloco R);
a rotina da BIOS do SGB só no console."""
import struct
import sys
import zlib

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
from sd_fixtures import lorom  # noqa: E402

CORE = b"\0" * 1024
IMAGE = 0x880000          # romprops.load_address do SGB e do GBC
GBCF = 0x7F80             # GBC_CFG_BLK_OFFSET
PADXLATE = (0x3CDE, 0x3CE1)
PADXLATE_CRC = 0x9402E61E
# sgb_bios_state(): as quatro BIOS do lado SNES que o firmware aceita
SGB_BIOS = ((0xCB176E45, 2), (0x8A4A174F, 1), (0x27A03C98, 1), (0x2E35EDBB, 1))


def _fix_checksum(rom: bytearray) -> bytes:
    hdr = 0x7FC0
    rom[hdr + 0x1C:hdr + 0x20] = b"\xff\xff\x00\x00"
    s = sum(rom) & 0xFFFF
    rom[hdr + 0x1C:hdr + 0x1E] = struct.pack("<H", s ^ 0xFFFF)
    rom[hdr + 0x1E:hdr + 0x20] = struct.pack("<H", s)
    return bytes(rom)


def _player(version: int) -> bytes:
    """Player falso (laço infinito) com o bloco GBCF de um player de verdade."""
    rom = bytearray(lorom("CICLONE PLAYER"))
    rom[GBCF:GBCF + 16] = b"GBCF" + bytes([version]) + bytes(11)
    return _fix_checksum(rom)


def _gb(cgb: int) -> bytes:
    rom = bytearray((i * 3) & 0xFF for i in range(32768))
    rom[0x134:0x144] = b"CICLONE GB".ljust(16, b"\0")
    rom[0x143] = cgb
    rom[0x146] = 0x03
    rom[0x147] = 0x00
    rom[0x148] = 0x00
    rom[0x149] = 0x00
    rom[0x14B] = 0x33
    return bytes(rom)


def _cgb_boot() -> bytes:
    for f in sorted((c.ROOT / "roms").rglob("*.bin")):
        d = f.read_bytes()
        if len(d) == 2304 and zlib.crc32(d) == 0x8113B4D8:
            return d
    raise c.Skip("cgb_boot.bin (SameBoy, CRC32 8113b4d8) not found under roms/")


def _sgb_bios() -> tuple[bytes, int]:
    for crc, ver in SGB_BIOS:
        try:
            return c.game_rom(crc, "Super Game Boy BIOS"), ver
        except c.Skip:
            continue
    raise c.Skip("no Super Game Boy BIOS (the SNES-side ROM) under roms/")


def _load(t, sd, name, experimental):
    m = t.menu(sd)
    m.goto(name)
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")                                   # Jogar
    if experimental:                               # o core GBC pergunta antes
        m.wait_text(c.tr("text_exp_l1"), frames=1800)
        m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot")
    return m


def test_rotate_row_in_the_sgb_menu(t):
    """X > Configurações > Opções SGB > "Rotate Game Boy buttons" -> Lig grava a chave."""
    sd = t.sd()
    m = t.menu(sd)
    m.press("X")
    for key in ("mtext_mm_cfg", "mtext_cfg_sgb", "mtext_gb_rotate"):
        row = c.encode_menu_text(c.tr(key))
        m.wait_text(row)
        for _ in range(24):
            if row in m.bar_row():
                break
            m.press("DOWN")
            m.step(4)
        assert row in m.bar_row(), (key, m.text())
        m.press("A")
        m.settle()
    want = c.encode_menu_text(c.tr("text_on"))
    for _ in range(4):                             # kv_onoff: Off, On -- UP goes forward
        if want in m.bar_row():
            break
        m.press("UP")
        m.step(10)
    assert want in m.bar_row(), m.text()
    m.press("A")
    m.settle()
    for _ in range(3):                             # SGB settings, settings, main menu
        m.press("B")
        m.settle()
    m.close()
    cfg = t.read(sd, "/sd2snes/config.yml").decode()
    assert "GbRotateButtons: true" in cfg, cfg


def _gbc_card(t, rotate: bool, version: int = 2):
    return t.sd(config=f"---\nGbRotateButtons: {'true' if rotate else 'false'}\n",
                extra={"/Game.gbc": _gb(0xC0), "/sd2snes/fpga_gbc.bi3": CORE,
                       "/sd2snes/gbc_snes.bin": _player(version), "/sd2snes/cgb_boot.bin": _cgb_boot()})


def test_gbc_player_gets_the_rotate_byte(t):
    for rotate in (True, False):
        m = _load(t, _gbc_card(t, rotate), "Game.gbc", experimental=True)
        blk = m.psram(IMAGE + GBCF, 8)
        assert blk[:5] == b"GBCF\x02", blk.hex()
        assert blk[6] == (1 if rotate else 0), (rotate, blk.hex(), m.fwlog()[-1500:])
        assert f"rotate={1 if rotate else 0}" in m.fwlog(), m.fwlog()[-1500:]
        m.close()


def test_gbc_version1_block_is_not_handed_the_byte(t):
    """Um player com o bloco versão 1 não conhece o +6: o firmware não escreve nele."""
    m = _load(t, _gbc_card(t, True, version=1), "Game.gbc", experimental=True)
    blk = m.psram(IMAGE + GBCF, 8)
    assert blk[:5] == b"GBCF\x01" and blk[6] == 0, blk.hex()
    m.close()


def _sgb_card(t, bios: bytes, ver: int, rotate: bool):
    return t.sd(config=f"---\nSGBBiosVersion: {ver}\nGbRotateButtons: {'true' if rotate else 'false'}\n",
                extra={"/Game.gb": _gb(0x00), "/sd2snes/fpga_sgb.bi3": CORE,
                       f"/sd2snes/sgb{ver}_boot.bin": bytes(256), f"/sd2snes/sgb{ver}_snes.bin": bios})


def test_sgb_bios_pad_routine_is_patched(t):
    bios, ver = _sgb_bios()
    off = next(o for o in PADXLATE if zlib.crc32(bios[o:o + 0x4E]) == PADXLATE_CRC)
    for rotate in (True, False):
        m = _load(t, _sgb_card(t, bios, ver, rotate), "Game.gb", experimental=False)
        code = m.psram(IMAGE + off, 0x4E)
        if rotate:
            assert code[0x11:0x16] == b"\xea" * 5, code.hex()
            assert code[:0x11] == bios[off:off + 0x11] and code[0x16:] == bios[off + 0x16:off + 0x4E]
            assert "SGB:  buttons rotated" in m.fwlog(), m.fwlog()[-1500:]
        else:
            assert code == bios[off:off + 0x4E], code.hex()
            assert "buttons rotated" not in m.fwlog()
        m.close()


def test_sgb_unknown_bios_is_left_alone(t):
    """BIOS que não tem a rotina conhecida (aqui um laço infinito): nada é escrito."""
    bios = lorom("CICLONE SGB BIOS")
    m = _load(t, _sgb_card(t, bios, 2, True), "Game.gb", experimental=False)
    for o in PADXLATE:
        assert m.psram(IMAGE + o, 0x4E) == bios[o:o + 0x4E]
    assert "unknown BIOS pad routine" in m.fwlog(), m.fwlog()[-1500:]
    m.close()
