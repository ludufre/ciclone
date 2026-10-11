"""Master System games on the SMS core, loaded through the menu.

The core runs as its real RTL (verilog/sd2snes_sms, Verilated by fpga_model/verilate_sms.sh),
with main.v's glue around it modelled in fpga_model/sms_model.cpp, and the SNES side is the
player of the same firmware tree (snes/sms/sms_snes.asm). So these tests cover the whole path:
the firmware's .sms load, the Z80 running the game from PSRAM, the VDP capture, the
translation to SNES buffers and the player putting them on screen.

A runner built without Verilator has no SMS core: every test here is skipped then.
"""
import ciclone as c

SONIC = 0x71EF3D88          # No-Intro, the USA/Europe/Brazil release
SMS_EXTS = (".sms",)


def _boot(t, rom: bytes, name: str = "Game.sms"):
    """Card with the game + the tree's player + a stand-in core file (the model does not read
    the bitstream); the info screen and the experimental-core question off, so A boots it."""
    player = c.sms_player()
    sd = t.sd(config="---\nShowGameInfo: 0\nWarnExperimental: false\n",
              extra={"/" + name: rom, "/sd2snes/fpga_sms.bi3": b"\0" * 1024, "/sd2snes/sms_snes.bin": player})
    m = t.menu(sd)
    m.goto(name)
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the game booting")
    if not m.sms():
        raise c.Skip("runner built without the SMS core (tools/sms_objs.sh: Verilator missing?)")
    return m


def _z80_card() -> bytes:
    """A 32 KB SMS program, Z80 machine code: mode 4, name table at $3800 filled with tile 1
    (a solid tile of colour 1), colour 1 = green, display on, then a tight loop."""
    regs = [0x04, 0x80,          # reg0: mode 4
            0x80, 0x81,          # reg1: display OFF while VRAM is written
            0xFF, 0x82,          # reg2: name table $3800
            0xFF, 0x83, 0xFF, 0x84,
            0xFF, 0x85,          # reg5: sprite table $3F00
            0xFB, 0x86,          # reg6: sprite tiles $0000
            0x00, 0x87,          # reg7: backdrop = colour 16
            0x00, 0x88, 0x00, 0x89,   # no scroll
            0xFF, 0x8A]
    pal = [0x00, 0x0C] + [0x00] * 30                 # colour 1 = %00 11 00 (green)
    tile = [0xFF, 0x00, 0x00, 0x00] * 8              # tile 1: plane 0 set = colour 1
    code = bytearray()
    code += bytes([0xF3, 0x31, 0xF0, 0xDF])          # di ; ld sp,$DFF0
    table = 0x100
    off = {"regs": table, "pal": table + 64, "tile": table + 128, "sat": table + 192}

    def otir(addr, n, port):
        return bytes([0x21, addr & 0xFF, addr >> 8, 0x06, n, 0x0E, port, 0xED, 0xB3])

    def setaddr(lo, hi):         # out ($BF),lo ; out ($BF),hi
        return bytes([0x3E, lo, 0xD3, 0xBF, 0x3E, hi, 0xD3, 0xBF])

    code += otir(off["regs"], len(regs), 0xBF)
    code += setaddr(0x00, 0xC0) + otir(off["pal"], 32, 0xBE)          # CRAM 0
    code += setaddr(0x20, 0x40) + otir(off["tile"], 32, 0xBE)         # VRAM $0020 = tile 1
    code += setaddr(0x00, 0x7F) + otir(off["sat"], 1, 0xBE)           # VRAM $3F00: $D0 ends the sprites
    code += setaddr(0x00, 0x78)                                       # VRAM $3800: the name table
    code += bytes([0x11, 0x00, 0x03,                                  # ld de,768
                   0x3E, 0x01, 0xD3, 0xBE,                            # L: ld a,1 ; out ($BE),a
                   0xAF, 0xD3, 0xBE,                                  #    xor a ; out ($BE),a
                   0x1B, 0x7A, 0xB3, 0x20, 0xF4])                     #    dec de ; ld a,d ; or e ; jr nz,L
    code += bytes([0x3E, 0xC0, 0xD3, 0xBF, 0x3E, 0x81, 0xD3, 0xBF])  # reg1 = $C0: display on
    code += bytes([0xC3, 0x00, 0x10])                                 # jp $1000
    assert len(code) <= table
    rom = bytearray(32768)
    rom[:len(code)] = code
    # idle: 16 KB of NOPs and a jump back -- the Z80 streams its code like a game does. NOT
    # `jr $`: a 2-byte loop flushes the core's prefetch on every pass, its ROM reads then win
    # every PSRAM slot the MCU leaves, and the translation's writes (below them in the
    # arbiter) never get one -- the picture would never come (a starvation the model shows
    # with the firmware's sram_reliable() polling on).
    rom[0x1000:0x5000] = bytes(0x4000)
    rom[0x5000:0x5003] = bytes([0xC3, 0x00, 0x10])
    rom[off["regs"]:off["regs"] + len(regs)] = bytes(regs)
    rom[off["pal"]:off["pal"] + 32] = bytes(pal)
    rom[off["tile"]:off["tile"] + 32] = bytes(tile)
    rom[off["sat"]] = 0xD0
    return bytes(rom)


def test_sms_program_draws_through_the_core(t):
    """A small SMS program (no commercial ROM): what it writes to the VDP reaches the SNES
    screen through the core's translation and the player."""
    m = _boot(t, _z80_card(), "Green.sms")
    m.wait(lambda: m.sms().get("display_on") == 1 and m.sms().get("shown", 0) >= 3, frames=600,
           what="the program turning the display on")
    m.step(30)
    assert m.sms_peek("cram", 0, 2) == bytes([0x00, 0x0C]), m.sms_peek("cram", 0, 32).hex()
    assert m.sms_peek("vreg", 2, 1) == b"\xff"
    # SMS colour %00 11 00 -> SNES BGR555 green 31 = $03E0 (sms_translate e2(): 3 -> 31)
    assert m.peek("cgram", 2, 2) == bytes([0xE0, 0x03]), m.peek("cgram", 0, 8).hex()
    r, g, b = m.rgb(128, 112)                     # the middle of the picture: tile 1, colour 1
    assert (r, g, b) == (0, 255, 0), (r, g, b)
    st = m.sms()
    assert st["tr_done"] >= 3 and st["z80_ce"] > 0, st


def test_sms_sonic_plays_green_hill(t):
    """Sonic 1 from the menu to Green Hill: title, button 1, the island map, then holding
    Right makes the level scroll (the VDP's horizontal scroll, which the title and the map
    never move), at a sane frame rate."""
    m = _boot(t, c.game_rom(SONIC, "Sonic The Hedgehog (SMS, USA/Europe/Brazil)", SMS_EXTS))
    m.wait(lambda: m.sms().get("display_on") == 1, frames=600, what="the title")
    m.step(120)
    m.press("B", hold=10)                          # button 1 = start
    m.hold("RIGHT")
    start = m.sms_peek("vreg", 8, 1)[0]
    m.wait(lambda: m.sms_peek("vreg", 8, 1)[0] != start, frames=900, every=10, what="Green Hill scrolling")
    f0, d0 = m.video()
    m.step(120)
    f1, d1 = m.video()
    m.release()
    m.shot(t.dir / "green_hill.png")
    # Green Hill's sky: the SNES backdrop is the SMS backdrop colour, not black
    assert m.peek("cgram", 0, 2) != b"\0\0", m.peek("cgram", 0, 32).hex()
    distinct = (d1 - d0) / ((f1 - f0) / 60.0988)
    assert distinct > 20, f"{distinct:.1f} distinct pictures/s while running"
    st = m.sms()
    assert st["tr_done"] > 300 and st["shown"] > 300, st
