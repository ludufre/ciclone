"""DSP-1 carts on the dsp core: the firmware picks fpga_dsp, streams dsp1b.bin into the uPD7725
and arms the address decoder; the uPD7725 itself runs in bsnes's NECDSP (fpga_model/behavioral.cpp
hands it the program and the windows of address.v).

Each test boots a synthetic ROM whose code asks the DSP-1 for one multiplication (command $00:
K * I >> 15) through one window and stores the result in WRAM, so the assert is the chip's answer.
Needs bios/dsp1b.bin (chip firmware never goes into the repo; the test skips without it).
"""
import struct

import ciclone as c

CORE = b"\0" * 1024                   # the model does not read the bitstream
K, I = 0x1234, 0x5678
PRODUCT = (K * I) >> 15
RESULT = 0x7E0010                     # 16-bit product, low byte first
DONE = 0x7E0012                       # $A5 once the code got there
PROBE = 0x7E0013                      # first byte read from the probe address
BANK4F_TITLE = "HINDSTRIKE"           # the one board smc.c maps with dsp_feat[15]: DSP-1 at bank $4F


def _long(op: int, addr: int) -> bytes:
    return bytes([op, addr & 0xFF, (addr >> 8) & 0xFF, addr >> 16])


def _program(dr: int, sr: int, probe: int, base: int = 0x8000) -> bytes:
    """65816 code (emulation mode, 8-bit) that reads `probe` into PROBE, sends command $00 with K
    and I through DR, waits on SR's RQM (bit 7) before each byte and stores the product."""
    def wr(v):
        return bytes([0xA9, v, 0x20]) + struct.pack("<H", base + wr_at)
    body = bytearray([0x78])                                   # sei
    body += _long(0xAF, probe) + _long(0x8F, PROBE)
    wr_at = rd_at = 0                                          # patched below
    calls = len(body)
    body += bytes(5 * 5 + 2 * 7 + 5 + 4 + 2)                   # room for the calls
    wr_at = len(body)
    sub = bytearray([0x48]) + _long(0xAF, sr) + bytes([0x10, 0xFA, 0x68]) + _long(0x8F, dr) + bytes([0x60])
    rd_at = wr_at + len(sub)
    sub += _long(0xAF, sr) + bytes([0x10, 0xFA]) + _long(0xAF, dr) + bytes([0x60])
    seq = bytearray()
    for v in (0x00, K & 0xFF, K >> 8, I & 0xFF, I >> 8):
        seq += wr(v)
    for i in range(2):
        seq += bytes([0x20]) + struct.pack("<H", base + rd_at) + _long(0x8F, RESULT + i)
    seq += bytes([0xA9, 0xA5]) + _long(0x8F, DONE) + bytes([0x80, 0xFE])   # done; bra *
    body[calls:calls + len(seq)] = seq
    assert calls + len(seq) <= wr_at
    return bytes(body) + bytes(sub)


def _rom(title: str, mapmode: int, chipset: int, code: bytes, hirom: bool = False,
         poke: dict | None = None) -> bytes:
    rom = bytearray(b"\xff" * 0x20000)                         # 128 KB
    at = 0x8000 if hirom else 0x0000                            # $00:8000
    rom[at:at + len(code)] = code
    for off, v in (poke or {}).items():
        rom[off] = v
    hdr = 0xFFC0 if hirom else 0x7FC0
    rom[hdr:hdr + 21] = title.encode("ascii")[:21].ljust(21, b" ")
    rom[hdr + 0x15] = mapmode
    rom[hdr + 0x16] = chipset
    rom[hdr + 0x17] = 0x07                                     # 128 KB
    rom[hdr + 0x18] = 0x00
    rom[hdr + 0x19] = 0x01
    rom[hdr + 0x1A] = 0x33
    rom[hdr + 0x1B] = 0x00
    rom[hdr + 0x3C:hdr + 0x3E] = struct.pack("<H", 0x8000)    # reset vector
    s = sum(rom) & 0xFFFF
    rom[hdr + 0x1C:hdr + 0x1E] = struct.pack("<H", s ^ 0xFFFF)
    rom[hdr + 0x1E:hdr + 0x20] = struct.pack("<H", s)
    return bytes(rom)


def _run(t, rom: bytes, fw: bytes | None = None):
    extra = {"/Dsp Game.sfc": rom, "/sd2snes/fpga_dsp.bi3": CORE}
    if fw is not None:
        extra["/sd2snes/dsp1b.bin"] = fw
    m = t.menu(t.sd(extra=extra))
    m.goto("Dsp Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")
    return m


def _product(t, rom: bytes):
    m = _run(t, rom, c.bios("dsp1b.bin", 8192))
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    m.wait(lambda: m.u8(DONE) == 0xA5, frames=600, what="the DSP-1 answer")
    return m, m.u16(RESULT)


def test_dsp1_lorom_low_window(t):
    """LoROM DSP-1 board ($20/$03): DR at $30-$3F:8000-BFFF, SR at $30-$3F:C000-FFFF."""
    m, got = _product(t, _rom("CICLONE DSP LOROM", 0x20, 0x03, _program(0x3F8000, 0x3FC000, 0x3FC000)))
    assert "DSPx game. Loading firmware image /sd2snes/dsp1b.bin" in m.fwlog(), m.fwlog()[-1500:]
    assert got == PRODUCT, f"{got:04x} != {PRODUCT:04x}"
    m.close()


def test_dsp1_lorom_high_window(t):
    """The same core also answers at $60-$6F:0000-3FFF (DR) / 4000-7FFF (SR), the window of the
    bigger LoROM boards."""
    m, got = _product(t, _rom("CICLONE DSP LOROM", 0x20, 0x03, _program(0x600000, 0x604000, 0x604000)))
    assert got == PRODUCT, f"{got:04x} != {PRODUCT:04x}"
    m.close()


def test_dsp1_hirom_window(t):
    """HiROM DSP-1 board ($21/$03): DR at $00-$0F:6000-6FFF, SR at 7000-7FFF (A0 = A12)."""
    m, got = _product(t, _rom("CICLONE DSP HIROM", 0x21, 0x03, _program(0x006000, 0x007000, 0x007000),
                              hirom=True))
    assert got == PRODUCT, f"{got:04x} != {PRODUCT:04x}"
    m.close()


def test_dsp1_at_bank_4f_on_the_board_that_wires_it_there(t):
    """One LoROM board ($30/$05) answers the DSP-1 at bank $4F instead of $30-$3F: the firmware
    matches its header and sets dsp_feat[15], and the core decodes $4F:8000-FFFF as the DSP."""
    m, got = _product(t, _rom(BANK4F_TITLE, 0x30, 0x05, _program(0x4F8000, 0x4FC000, 0x4FC000)))
    assert "chipfeat <= 32772" in m.fwlog(), m.fwlog()[-1500:]     # 4 wait states + bit 15
    assert got == PRODUCT, f"{got:04x} != {PRODUCT:04x}"
    m.close()


def test_bank_4f_stays_rom_on_any_other_dsp1_board(t):
    """The same header shape with another title keeps bank $4F as plain LoROM: the probe at
    $4F:C000 reads the ROM byte there (offset $1C000 of a 128 KB image), not the DSP status, and
    the DSP still answers at $3F."""
    rom = _rom("CICLONE DSP OTHER", 0x30, 0x05, _program(0x3F8000, 0x3FC000, 0x4FC000), poke={0x1C000: 0x5A})
    m, got = _product(t, rom)
    assert "chipfeat <= 4" in m.fwlog(), m.fwlog()[-1500:]
    assert m.u8(PROBE) == 0x5A, f"{m.u8(PROBE):02x}"
    assert got == PRODUCT, f"{got:04x} != {PRODUCT:04x}"
    m.close()


def test_dsp1_game_without_dsp1b_bin_is_refused(t):
    """No dsp1b.bin on the card: the pre-check names the missing file and the game never boots."""
    m = _run(t, _rom("CICLONE DSP LOROM", 0x20, 0x03, _program(0x3F8000, 0x3FC000, 0x3FC000)))
    m.wait_text("dsp1b.bin", frames=1200)
    assert "going to snes main loop" not in m.fwlog()
    m.close()
