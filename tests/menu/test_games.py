"""Real games, loaded the real way (card -> Play -> firmware) and played on the FPGA model's mappers.

The ROMs are commercial and never go into the repo: each test looks its dump up by CRC32 under
$CICLONE_ROMS (see ciclone.game_rom) and is skipped when it is not there. Asserts read the game's
own WRAM state (game mode, player position), so they do not depend on pixels or exact frame counts.
"""
import ciclone as c

SMW = 0xB19ED489    # Super Mario World (USA): LoROM, 512 KB, no coprocessor
DKC3 = 0x448EEC19   # Donkey Kong Country 3 (USA) (En,Fr): HiROM, 4 MB, no coprocessor

SMW_MODE = 0x7E0100       # game mode: $07 title, $08 file select, $0E overworld, $14 level
SMW_MARIO_X = 0x7E0094
SMW_FRAME = 0x7E0013      # frame counter: stands still while the game loop does not run
DKC3_SCREEN = 0x7E0436    # front-end screen index (x2): $02 select game, $04 play mode, $06 name, $08 map

MENU_COMBO = ("L", "R", "Y", "LEFT")   # CFG.ingame_buttons_menu default ($4230)
TAB_ON = (82, 0, 255)                  # the in-game menu's highlighted tab (first tab at 12,10)


def _play(t, name, rom):
    m = t.menu(t.sd(extra={f"/{name}": rom}))
    m.goto(name)
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")                                        # Play
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    return m


def _press_until(m, btn, pred, what, tries=10, after=90):
    for _ in range(tries):
        if pred():
            return
        m.press(btn, hold=6, after=after)
    assert pred(), f"{what}: still not there after {tries}x {btn}"


def _smw_in_yoshis_house(t):
    m = _play(t, "Super Mario World.sfc", c.game_rom(SMW, "Super Mario World (USA)"))
    mode = lambda: m.u8(SMW_MODE)                       # noqa: E731
    m.wait(lambda: mode() == 0x07, frames=900, what="the title screen")
    _press_until(m, "START", lambda: mode() == 0x14, "the intro level")
    m.step(600)                                         # the welcome message only closes once drawn
    _press_until(m, "B", lambda: mode() == 0x0E, "the overworld", after=120)
    _press_until(m, "Y", lambda: mode() == 0x14, "Yoshi's House", after=120)
    m.step(60)
    return m


def _walk_right(m):
    x0 = m.u16(SMW_MARIO_X)
    m.hold("RIGHT")
    m.step(60)
    m.release()
    assert m.u16(SMW_MARIO_X) > x0 + 32, (x0, m.u16(SMW_MARIO_X))


def test_smw_lorom_plays(t):
    """LoROM: title, file select, the intro level, the overworld, a level, and the pad moves Mario."""
    _walk_right(_smw_in_yoshis_house(t))


def test_ingame_menu_opens_and_game_resumes(t):
    """The in-game menu over SMW, all real code: the FPGA model hijacks the NMI vector into the
    firmware's stub at $2A10, the savestate handler matches the combo and opens igmenu.bin from
    PSRAM; B closes it, the PPU/CPU registers come back from the ctx shadows and the game runs on."""
    m = _smw_in_yoshis_house(t)          # long past the 10 s hook holdoff after the game's reset
    frame = lambda: m.u8(SMW_FRAME)                     # noqa: E731
    m.hold(*MENU_COMBO)
    m.step(30)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == TAB_ON, frames=120, what="the in-game menu")
    f = frame()
    m.step(30)
    assert frame() == f, "the game loop kept running under the menu"
    m.press("R", hold=6, after=40)                      # R: last tab
    assert m.rgb(12, 10) != TAB_ON, "the tab bar did not follow R"
    m.press("B", hold=6, after=60)                      # close
    f = frame()
    m.step(10)
    assert frame() != f, "the game did not resume"
    m.step(60)
    _walk_right(m)


def test_dkc3_hirom_4mb_plays(t):
    """HiROM, 4 MB (the whole PSRAM window): intro, title and the front end down to the world map."""
    m = _play(t, "DKC3.sfc", c.game_rom(DKC3, "Donkey Kong Country 3 (USA) (En,Fr)"))
    assert "loaded 4194304 bytes" in m.fwlog()
    screen = lambda: m.u8(DKC3_SCREEN)                  # noqa: E731
    m.step(1300)                                        # Rare logo + intro
    _press_until(m, "START", lambda: screen() == 0x02, "Select Game", after=120)
    _press_until(m, "A", lambda: screen() == 0x04, "Choose Play Mode", after=120)
    _press_until(m, "A", lambda: screen() == 0x06, "Enter Name", after=240)
    _press_until(m, "START", lambda: screen() == 0x08, "the world map", after=300)
