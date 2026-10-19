"""Real games, loaded the real way (card -> Play -> firmware) and played on the FPGA model's mappers.

The ROMs are commercial and never go into the repo: each test looks its dump up by CRC32 under
roms/ (git-ignored) or $CICLONE_ROMS (see ciclone.game_rom) and is skipped when it is not there.
Asserts read the game's own WRAM state (game mode, player position), so they do not depend on
pixels or exact frame counts.
"""
import re
import time
from pathlib import Path

import ciclone as c

SMW = 0xB19ED489    # Super Mario World (USA): LoROM, 512 KB, no coprocessor
DKC3 = 0x448EEC19   # Donkey Kong Country 3 (USA) (En,Fr): HiROM, 4 MB, no coprocessor
DKC1 = 0xC946DCA0   # Donkey Kong Country (USA) v1.0
DKC2 = 0x006364DB   # Donkey Kong Country 2 - Diddy's Kong Quest (USA) (En,Fr) v1.0
KI = 0x252C1DA7     # Killer Instinct (USA): HiROM, 4 MB, no coprocessor
KI_R1 = 0x09E9A04E  # Killer Instinct (USA) (Rev 1)
KI_EU = 0x3D7252D4  # Killer Instinct (Europe)
HIND = 0xDA955CF2       # Hind Strike (clean dump): LoROM DSP-1, the DSP answered at bank $4F
HIND_CRACK = 0x0C62A02F # Hind Strike (cracked): the same game patched to talk to the DSP at $3F

SMW_MODE = 0x7E0100       # game mode: $07 title, $08 file select, $0E overworld, $14 level
SMW_MARIO_X = 0x7E0094
SMW_FRAME = 0x7E0013      # frame counter: stands still while the game loop does not run
SMW_PAUSE = 0x7E13D4      # 1 = paused (START)
SMW_LIVES = 0x7E0DBE      # lives - 1
SMW_STATE = "/sd2snes/states/SU/Super Mario World01.state"
DKC3_SCREEN = 0x7E0436    # front-end screen index (x2): $02 select game, $04 play mode, $06 name, $08 map

MENU_COMBO = {"L", "R", "Y", "LEFT"}   # CFG.ingame_buttons_menu default ($4230)
TAB_ON = (82, 0, 255)                  # the in-game menu's highlighted tab (first tab at 12,10)


def _play(t, name, rom, extra=None, env=None):
    m = t.menu(t.sd(extra={f"/{name}": rom, **(extra or {})}), env=env)
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


def _smw_in_yoshis_house(t, extra=None, env=None):
    m = _play(t, "Super Mario World.sfc", c.game_rom(SMW, "Super Mario World (USA)"), extra, env)
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
    combo = m.menu_combo()                              # what the window's M key presses
    assert set(combo) == MENU_COMBO, combo
    m.hold(*combo)
    m.step(20)                                          # as long as M holds it (MENU_HOLD)
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


def _walk(m, btn, frames=60):
    m.hold(btn)
    m.step(frames)
    m.release()
    m.step(10)


def test_savestate_save_and_load(t):
    """Start+R saves (the handler freezes the game in the hook, the FPGA copier stages the WRAM
    mirror, VRAM/CGRAM/OAM are read back, the MCU writes the 320 KB image to the card); Start+L
    replays it from PSRAM: Mario is back where he was, paused as he was."""
    m = _smw_in_yoshis_house(t)
    x = lambda: m.u16(SMW_MARIO_X)                      # noqa: E731
    _walk(m, "RIGHT", 30)
    saved = x()
    m.hold("START", "R")                                # default IngameButtonsSavestate
    m.step(20)
    m.release()
    m.wait(lambda: f"file_open ({SMW_STATE}, 0a)" in m.fwlog(), frames=600, what="the state file")
    m.step(60)
    assert m.u8(SMW_PAUSE) == 1                         # the START of the combo paused SMW
    _press_until(m, "START", lambda: m.u8(SMW_PAUSE) == 0, "unpaused", tries=3, after=40)
    _walk(m, "LEFT")
    assert x() < saved - 32, (saved, x())
    m.hold("START", "L")                                # default IngameButtonsLoadstate
    m.step(20)
    m.release()
    m.step(60)
    assert x() == saved and m.u8(SMW_PAUSE) == 1, (saved, x(), m.u8(SMW_PAUSE))
    _press_until(m, "START", lambda: m.u8(SMW_PAUSE) == 0, "unpaused after the load", tries=3, after=40)
    _walk(m, "LEFT")
    assert x() < saved - 32, "the game did not run on after the load"
    sd = m.sd
    m.close()
    state = t.read(sd, SMW_STATE)
    assert state is not None and len(state) == 0x50000, len(state or b"")


def test_gesture_reset_to_menu(t):
    """L+R+Select+X: the stub echoes the gesture ($81) to the MCU and parks the SNES (nmi_stop);
    the firmware brings the menu back up."""
    m = _smw_in_yoshis_house(t)
    m.hold("L", "R", "SEL", "X")
    m.step(30)
    m.release()
    m.wait(lambda: "snes loop cmd=81" in m.fwlog(), frames=300, what="the gesture at the MCU")
    m.wait(lambda: "Super Mario World.sfc" in m.list_names(), frames=1200, what="the menu")


def test_gesture_reset_game(t):
    """L+R+Start+Select ($80): the firmware pulses reset and the game starts over."""
    m = _smw_in_yoshis_house(t)
    m.hold("L", "R", "START", "SEL")
    m.step(30)
    m.release()
    m.wait(lambda: "snes loop cmd=80" in m.fwlog(), frames=300, what="the gesture at the MCU")
    m.wait(lambda: m.u8(SMW_MODE) < 0x07, frames=300, what="the reset")
    m.wait(lambda: m.u8(SMW_MODE) == 0x07, frames=900, what="the title screen again")


def test_wram_cheat(t):
    """A WRAM cheat from the game's .yml: the firmware installs the patch code in SNESCMD and the
    NMI stub runs it every frame (branch nmi_patches), pinning Mario's lives."""
    yml = b'---\n- Name: "Lives"\n  Enabled: true\n  Code:\n  - "7E0DBE09"\n'
    m = _play(t, "Super Mario World.sfc", c.game_rom(SMW, "Super Mario World (USA)"),
              {"/sd2snes/cheats/SU/Super Mario World.yml": yml})
    assert "RAM cheat #0: 7e0dbe 09" in m.fwlog()
    m.wait(lambda: m.u8(SMW_LIVES) == 9, frames=900, what="the pinned lives")   # after the holdoff



def test_savestate_restores_the_music_bank(t):
    """savestate_fixes.yml A0DA: a state does not carry the APU, and SMW uploads a different music
    bank for levels and for the overworld. Saved in Yoshi's House and loaded from the overworld,
    the fix re-runs the game's own upload for the loaded area on LOAD (not on save), so the APU
    holds the level bank again instead of playing an overworld song under the level."""
    m = _smw_in_yoshis_house(t)
    level_aram = m.aram()
    m.hold("START", "R")
    m.step(20)
    m.release()
    m.wait(lambda: f"file_open ({SMW_STATE}, 0a)" in m.fwlog(), frames=600, what="the state file")
    m.step(30)
    _press_until(m, "START", lambda: m.u8(SMW_PAUSE) == 0, "unpaused", tries=3, after=40)
    m.hold("RIGHT")                                     # out of the house: overworld, its music bank
    m.wait(lambda: m.u8(SMW_MODE) == 0x0E, frames=1200, what="the overworld")
    m.release()
    m.step(120)
    ow_aram = m.aram()
    assert sum(x != y for x, y in zip(level_aram, ow_aram)) > 1000   # the two banks really differ
    m.hold("START", "L")
    m.step(20)
    m.release()
    m.step(90)
    assert m.u8(SMW_MODE) == 0x14
    back, _ = m.bank_match(m.aram(), level_aram, ow_aram)
    assert back > 0.95, f"only {back:.0%} of the level bank is back in ARAM"
    _press_until(m, "START", lambda: m.u8(SMW_PAUSE) == 0, "unpaused after the load", tries=3, after=40)
    _walk(m, "LEFT")                                    # and the game runs on


def _dkc3_in_wrinklys_cabin(t, env=None):
    m = _play(t, "DKC3.sfc", c.game_rom(DKC3, "Donkey Kong Country 3 (USA) (En,Fr)"), env=env)
    screen = lambda: m.u8(DKC3_SCREEN)                  # noqa: E731
    m.step(1300)
    _press_until(m, "START", lambda: screen() == 0x02, "Select Game", after=120)
    _press_until(m, "A", lambda: screen() == 0x04, "Choose Play Mode", after=120)
    _press_until(m, "A", lambda: screen() == 0x06, "Enter Name", after=240)
    m.press("START", hold=6, after=700)                 # the map, and a new game walks into the cabin
    m.step(400)
    return m


def test_savestate_restores_the_song_dkc3(t):
    """savestate_fixes.yml B28C (tools/ssfix/dkc3_b28c.s): Rare's driver holds one song, uploaded per
    scene, and the state does not carry it. Saved in Wrinkly's cabin and loaded from the map, the
    fix replays the cabin's song -- from a one-shot NMI routine after the hook, since the song
    tables sit in $ED/$EE, behind the hook's $C0-$FF window. DKC3's savestate combos are X+R/X+L."""
    m = _dkc3_in_wrinklys_cabin(t)
    cabin = m.aram()
    m.hold("X", "R")
    m.step(20)
    m.release()
    m.wait(lambda: "DKC301.state, 0a" in m.fwlog(), frames=900, what="the state file")
    m.step(60)
    for _ in range(8):                                  # through Wrinkly's lines...
        m.press("A", hold=6, after=90)
    for _ in range(5):                                  # ...and out, to the map and its song
        m.press("B", hold=6, after=150)
    m.step(200)
    on_map = m.aram()
    assert sum(x != y for x, y in zip(cabin, on_map)) > 1000
    m.hold("X", "L")
    m.step(20)
    m.release()
    m.step(250)                                         # the hook, then the upload (~50 frames)
    back, stale = m.bank_match(m.aram(), cabin, on_map)
    # Rare's driver keeps rewriting its own ARAM while a song plays, so "the same song at another
    # moment" tops out near 93% here (without the fix it reads 0% cabin / 93% map)
    assert back > 0.85 and stale < 0.2, f"ARAM after the load: {back:.0%} cabin song, {stale:.0%} map song"
    assert m.u16(0x7E004A) != 0x0110, "the one-shot NMI routine is still hooked"


def _dk_song_back_after_load(t, crc, what, name, song, map_song, level_song, dispatch, mode_song=None):
    """Save on the world map, walk into the first level (another song), load: the fix must replay
    the map's song. Measured on what the load rewrote in ARAM, minus what the driver rewrites on
    its own while a song plays (echo buffer, track state)."""
    m = _play(t, name, c.game_rom(crc, what))
    now = lambda: m.u16(song)                           # noqa: E731
    m.step(600)
    for _ in range(3):
        m.press("START", hold=6, after=200)
    if mode_song is not None:
        m.wait(lambda: now() == mode_song, frames=900, what="the mode screen")
    _press_until(m, "A", lambda: now() == map_song, "the map", after=300)
    m.step(200)
    on_map = m.aram()
    m.step(60)
    noise = m.volatile(on_map, m.aram())
    m.hold("X", "R")
    m.step(20)
    m.release()
    m.wait(lambda: f"{Path(name).stem}01.state, 0a" in m.fwlog(), frames=900, what="the state file")
    m.step(60)
    _press_until(m, "A", lambda: now() == level_song, "the first level", after=300)
    m.step(300)
    in_level = m.aram()
    for _ in range(4):                                  # the handler's post-save cooldown can eat
        m.hold("X", "L")                                # the first load after few button presses
        m.step(20)
        m.release()
        m.step(300)
        if now() != level_song:
            break
    assert now() == map_song, "the load did not happen"
    n, frac = m.load_match(m.aram(), in_level, on_map, noise)
    assert n > 2000 and frac > 0.9, f"the load rewrote {n} ARAM bytes, {frac:.0%} of them the map's"
    assert m.u16(dispatch) != 0x0110, "the one-shot NMI routine is still hooked"


def test_savestate_restores_the_song_dkc1(t):
    """savestate_fixes.yml EF80/D17C (tools/ssfix/dkc1_ef80.s): replays $0523 through $B99036."""
    _dk_song_back_after_load(t, DKC1, "Donkey Kong Country (USA)", "DKC1.sfc", 0x7E0523, 0x0C, 0x00, 0x7E001C)


def test_savestate_restores_the_song_dkc2(t):
    """savestate_fixes.yml 1202/9860 (tools/ssfix/dkc2_1202.s): replays $1C through $B5800C."""
    _dk_song_back_after_load(t, DKC2, "Donkey Kong Country 2 - Diddy's Kong Quest (USA) (En,Fr)", "DKC2.sfc",
                             0x7E001C, 0x01, 0x06, 0x7E0020, mode_song=0x18)



def _ki_boot(t, sd):
    m = t.menu(sd)
    m.goto("KI.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")                                        # Play
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    m.step(600)
    return m


def _ki_song_back_after_load(t, crc, what, song_at, pending_at, echo_at):
    """Save in the first fight, load from the title screen of another session (the APU holds the
    title song): the fix must put the fight's song back in the APU, and the game must keep answering
    START -- pause and unpause both send a command, and a command nobody answers hangs the game.
    song_at: the song the game believes the APU holds; pending_at: the song its NMI epilogue uploads
    next; echo_at: the command counter it waits for on $2140."""
    sd = t.sd(extra={"/KI.sfc": c.game_rom(crc, what)})
    m = _ki_boot(t, sd)
    song = lambda: m.u16(song_at)                       # noqa: E731
    seen = [song()]                                     # title, then the menus, then the fight
    for _ in range(12):
        if len(seen) == 3:
            break
        m.press("START", hold=6, after=240)
        if song() != seen[-1]:
            seen.append(song())
    assert len(seen) == 3, f"never reached a fight: songs {seen}"
    m.step(600)
    fight = m.aram()
    m.step(60)
    noise = m.volatile(fight, m.aram())
    m.hold("START", "R")                                # the default save combo (START also pauses)
    m.step(20)
    m.release()
    m.wait(lambda: "KI01.state, 0a" in m.fwlog(), frames=900, what="the state file")
    m.step(60)
    m.close()

    m = _ki_boot(t, sd)                                 # another session: the APU holds the title song
    song = lambda: m.u16(song_at)                       # noqa: E731
    assert song() == seen[0], f"not on the title screen: song {song():04x}"
    title = m.aram()
    for _ in range(4):                                  # START moves the title on; the load lands
        m.hold("START", "L")                            # once the game's own song upload lets the
        m.step(20)                                      # hook in again
        m.release()
        m.step(300)
        if song() == seen[2]:
            break
    assert song() == seen[2], "the load did not happen"
    m.step(300)
    assert m.u16(pending_at) == 0, "the song upload is still pending"
    n, frac = m.load_match(m.aram(), title, fight, noise)
    assert n > 2000 and frac > 0.85, f"the load rewrote {n} ARAM bytes, {frac:.0%} of them the fight's"
    for i in range(6):                                  # unpause, pause, ... each one is a command
        echo = m.u8(echo_at)
        m.press("START", hold=6, after=120)
        assert m.u8(echo_at) != echo, f"START #{i + 1} sent nothing: the game is stuck on the APU"


def test_savestate_restores_the_song_ki(t):
    """savestate_fixes.yml 45C0 (tools/ssfix/ki_45c0.s): the game tracks in WRAM which song and sample
    pack the APU holds and sends every command with an untimed counter handshake."""
    _ki_song_back_after_load(t, KI, "Killer Instinct (USA)", 0x7E17DA, 0x7E00AA, 0x7E17DC)


def test_savestate_restores_the_song_ki_rev1(t):
    """savestate_fixes.yml 757A (tools/ssfix/ki_757a.s): the same driver, variables two bytes up."""
    _ki_song_back_after_load(t, KI_R1, "Killer Instinct (USA) (Rev 1)", 0x7E17DC, 0x7E00AA, 0x7E17DE)


def test_savestate_restores_the_song_ki_europe(t):
    """savestate_fixes.yml 850A (tools/ssfix/ki_850a.s): the same driver, pending song at $AB."""
    _ki_song_back_after_load(t, KI_EU, "Killer Instinct (Europe)", 0x7E17DC, 0x7E00AB, 0x7E17DE)


HX_PAD2 = 0xFF07E4        # the stub's controller-2 sample (BSRAM)


def _play_smw_pad2(t):
    m = t.menu(t.sd(config="---\nEnableIngamePad2: true\n",
                    extra={"/Super Mario World.sfc": c.game_rom(SMW, "Super Mario World (USA)")}))
    m.goto("Super Mario World.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    m.step(900)                                         # past the 10 s hook holdoff
    return m


def test_pad2_sample_follows_the_pad(t):
    """EnableIngamePad2: the stub's controller-2 sample tracks the pad on every frame. SMW's
    NMI lands inside the auto-joypad fill every frame; skipping the read there (instead of
    waiting for the fill to end) left the sample stuck and controller 2 dead in the game."""
    m = _play_smw_pad2(t)
    miss = []
    for i in range(60):
        held = (i // 2) % 2                             # X held two frames, released two
        if held:
            m.hold("X", pad=2)
        else:
            m.release(pad=2)
        m.step(1)
        got = int.from_bytes(m.psram(HX_PAD2, 2), "little") & 0x0040
        if bool(got) != bool(held):
            miss.append(i)
    assert not miss, f"controller-2 sample stale on frames {miss}"


def test_pad2_gesture_reset_to_menu(t):
    """The back-to-menu gesture (L+R+Select+X) on controller 2, held briefly."""
    m = _play_smw_pad2(t)
    m.hold("L", "R", "SEL", "X", pad=2)
    m.step(6)
    m.release(pad=2)
    m.wait(lambda: "snes loop cmd=81" in m.fwlog(), frames=300, what="the gesture at the MCU")
    m.wait(lambda: "Super Mario World.sfc" in m.list_names(), frames=1200, what="the menu")


def test_ingame_menu_closes_at_once_with_a_mouse_in_port_1(t):
    """A mouse in port 1 (Mario Paint) and the in-game menu opened and closed from controller 2:
    the close waits for the pads to be released, and a mouse never reads zero (its ID lives in
    the low nibble), so before the ID filter every close sat out the drain's 3 s ceiling."""
    m = t.menu(t.sd(config="---\nEnableIngamePad2: true\n",
                    extra={"/Super Mario World.sfc": c.game_rom(SMW, "Super Mario World (USA)")}),
               env={"CICLONE_PORT1": "mouse"})
    m.goto("Super Mario World.sfc", pad=2)              # the menu ignores the mouse, as on a console
    m.press("A", pad=2)
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A", pad=2)
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    m.step(900)                                         # past the 10 s hook holdoff
    m.hold(*MENU_COMBO, pad=2)
    m.step(20)
    m.release(pad=2)
    m.wait(lambda: m.rgb(12, 10) == TAB_ON, frames=120, what="the in-game menu")
    m.step(30)
    frame = lambda: m.u8(SMW_FRAME)                     # noqa: E731
    m.press("B", pad=2, hold=6, after=0)
    f = frame()
    for n in range(240):
        m.step(1)
        if frame() != f:
            break
    assert n < 30, f"the game resumed {n} frames after B"


def test_pad2_savestate_saves_once(t):
    """Start+R on controller 2, held for a second: one save. The save's second opinion re-read
    the live $4218 (controller 1, idle) and rejected every port-2 match, and the wait for the
    combo's release watched port 1 only, so a held port-2 combo would have saved again."""
    m = _play_smw_pad2(t)
    m.hold("START", "R", pad=2)
    m.step(60)
    m.release(pad=2)
    m.step(300)
    saves = m.fwlog().count(f"file_open ({SMW_STATE}, 0a)")
    assert saves == 1, f"{saves} state writes"


def _title_colors(m) -> int:
    """Distinct colours on an 8x7 grid of the screen: the black screen of a game stuck on its
    coprocessor has one, a drawn title screen has many."""
    return len({m.rgb(16 + x * 32, 16 + y * 32) for x in range(8) for y in range(7)})


def _hind_strike(t, crc, what, chipfeat):
    extra = {"/sd2snes/dsp1b.bin": c.bios("dsp1b.bin", 8192), "/sd2snes/fpga_dsp.bi3": b"\0" * 1024}
    m = _play(t, "Hind Strike.sfc", c.game_rom(crc, what), extra)
    assert f"chipfeat <= {chipfeat}" in m.fwlog(), m.fwlog()[-1500:]
    # the game talks to the DSP-1 before drawing anything: without it the screen stays black
    m.wait(lambda: _title_colors(m) >= 8, frames=1800, what="the title screen")
    m.close()


def test_hind_strike_clean_dump_dsp_at_bank_4f(t):
    """The original dump reaches its title screen: the firmware sets dsp_feat[15] (4 wait states
    + bit 15) and the core answers the DSP-1 at $4F."""
    _hind_strike(t, HIND, "Hind Strike (clean dump)", 32772)


def test_hind_strike_cracked_dsp_at_3f(t):
    """The cracked dump moved every DSP access to $3F: plain DSP-1 LoROM, no bank-$4F bit."""
    _hind_strike(t, HIND_CRACK, "Hind Strike (cracked)", 4)


def _ovl_text(m):
    """The in-game menu's text: it draws straight into VRAM (mode 5, BG2 at word $5000 = the
    even columns, BG1 at $5800 = the odd ones, 32 words a row), not into the menu's buffers."""
    bg2 = m.peek("vram", 0x5000 * 2, 32 * 32 * 2)
    bg1 = m.peek("vram", 0x5800 * 2, 32 * 32 * 2)
    rows = []
    for y in range(32):
        line = []
        for x in range(64):
            buf = bg2 if x % 2 == 0 else bg1
            off = (y * 32 + x // 2) * 2
            tile = (buf[off] | buf[off + 1] << 8) & 0x3FF
            ch = tile >> 1 if tile < 0x200 else 0
            line.append(c.FONT.get(ch, " " if ch < 32 else "?"))
        rows.append("".join(line).rstrip())
    return "\n".join(rows)


def test_ingame_saves_tab_shows_each_slots_date(t):
    """The SAVES tab of the in-game menu: the date of each slot's save next to it, from the
    saves block the firmware stages at the game load, in the menu language's order."""
    srm = "/sd2snes/saves/SU/Super Mario World.02.srm"
    t0 = time.mktime((2026, 10, 15, 13, 42, 0, 0, 0, -1))
    m = _smw_in_yoshis_house(t, extra={srm: (b"\0" * 2048, t0)})
    m.hold(*m.menu_combo())
    m.step(20)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == TAB_ON, frames=120, what="the in-game menu")
    for _ in range(6):
        if "10/15/2026 13:42" in _ovl_text(m):
            break
        m.press("RIGHT", hold=6, after=40)
    text = _ovl_text(m)
    row = next((r for r in text.splitlines() if "10/15/2026 13:42" in r), None)
    assert row is not None and re.search(r"2\s+10/15/2026 13:42", row), text
    # only the active slot's "SLOT n" is green: slot 2's date stays plain text
    lines = text.splitlines()
    y2 = lines.index(row)
    y1 = next(i for i, r in enumerate(lines) if re.search(r"SLOT\s+1\b", r))
    assert _ovl_pal(m, row.index("10/15/2026"), y2) == 0, "the date came out green"
    assert _ovl_pal(m, lines[y1].index("SLOT"), y1) == 2, "the active slot is not green"
    assert _ovl_pal(m, row.index("SLOT"), y2) == 0


def _ovl_pal(m, x, y):
    """Palette of in-game menu cell x, y (the tilemap word's bits 10-12, see _ovl_text)."""
    base = 0x5000 if x % 2 == 0 else 0x5800
    w = m.peek("vram", (base + y * 32 + x // 2) * 2, 2)
    return (w[0] | w[1] << 8) >> 10 & 7


SS_SLOT = 0xFE100F                       # the savestate handler's slot (CS_SLOT), 1..4
SMW_SLOT = "/sd2snes/saves/SU/Super Mario World.slot"


def test_savestate_slot_picked_in_game_is_remembered(t):
    """Select+Right picks savestate slot 2 in the game; leaving it writes that to the game's
    per-game file (SaveStateSlot of saves/<BB>/<stem>.yml; slot 1 of the battery save is no
    line), and the next start comes back on it."""
    rom = c.game_rom(SMW, "Super Mario World (USA)")
    sd = t.sd(config="---\nEnableSavestateSlots: true\n", extra={"/Super Mario World.sfc": rom})
    m = t.menu(sd)
    m.goto("Super Mario World.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    assert m.psram(SS_SLOT, 1)[0] & 0x7F == 1
    m.wait(lambda: m.u8(SMW_MODE) == 0x07, frames=900, what="the title screen")
    m.step(600)                                         # past the hooks' holdoff after the boot
    m.hold("SEL", "RIGHT")                              # default IngameButtonsChangeState + Right
    m.step(20)
    m.release()
    m.wait(lambda: m.psram(SS_SLOT, 1)[0] & 0x7F == 2, frames=300, what="slot 2")
    covers = m.fwlog().count("cover: try /Super Mario World.cov")
    m.hold("L", "R", "SEL", "X")                        # back to the menu
    m.step(30)
    m.release()
    m.wait(lambda: "Super Mario World.sfc" in m.list_names(), frames=1200, what="the menu")
    # the list shows some 20-40 frames before the menu loop reads the pad again (a press in between
    # is lost, on master too): wait for it to ask for the selected game's cover
    m.wait(lambda: m.fwlog().count("cover: try /Super Mario World.cov") > covers
           and m.u8("cover_request_pending") == 0, frames=300, what="the menu loop")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card again")
    m.press("A")
    m.wait(lambda: m.fwlog().count("going to snes main loop") == 2, frames=1800, what="the reboot")
    assert m.psram(SS_SLOT, 1)[0] & 0x7F == 2, "the game did not start on the slot picked last time"
    m.close()
    yml = t.read(sd, SMW_SLOT.replace(".slot", ".yml"))
    assert yml is not None and b"SaveStateSlot: 2\r\n" in yml and b"SaveGameSlot" not in yml, yml
    assert t.read(sd, SMW_SLOT) is None
