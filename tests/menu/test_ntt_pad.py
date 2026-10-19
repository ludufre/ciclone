"""NTT Data Keypad (NDK10) in the menu and in-game (CICLONE_PORT1/2=ntt).

The keypad is a standard pad plus a number pad. Its first 16 serial bits are the pad's
except the signature: bits 13-16 = 0100, so the low nibble of $4218/$421A reads 4 instead
of 0. The menu's controller filter took every non-zero nibble as "not a pad" (the mouse has
its own exception), so the keypad worked in games and was dead in the menu; the in-game
shell, the guide viewer and the close drain filtered it the same way, and the hook gestures
(compared EXACTLY in the FPGA against the word the nmihook stub stores) never matched it.

The fix: PAD_ID_NOTPAD ($000b) accepts nibble 0 and 4 and drops the nibble; the menu
publishes port 1's ID nibble at PAD1_ID ($FF07FE) and the firmware routes the stub's pad
store through hx_pad when it is the keypad, so the gestures see the word without it."""
import ciclone as c

ROOT = ["Empty Folder/", "MSU Game/", "Two Games/", "Test Game.sfc"]
NTT1 = {"CICLONE_PORT1": "ntt"}
NTT2 = {"CICLONE_PORT2": "ntt"}
PAD1_ID = 0xFF07FE          # snes/memmap.i65 PAD1_ID: port 1's ID nibble, written by read_pad
PAD_ID_NTT = 4

SMW = 0xB19ED489            # Super Mario World (USA): LoROM, 512 KB, no coprocessor
SMW_FRAME = 0x7E0013        # frame counter: stands still while the game loop does not run
MENU_COMBO = {"L", "R", "Y", "LEFT"}   # CFG.ingame_buttons_menu default ($4230)
TAB_ON = (82, 0, 255)       # the in-game menu's highlighted tab (first tab at 12,10)


def _browse(m, pad: int):
    """Down to the ROM, the context menu (Y) and back (B), the main menu (X) and back."""
    m.goto("Test Game.sfc", pad=pad)
    assert m.selected() == "Test Game.sfc", m.selected()
    m.press("Y", pad=pad)
    m.settle()
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), m.text()
    m.press("B", pad=pad)
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF
    assert m.selected() == "Test Game.sfc"
    m.press("X", pad=pad)
    m.wait(lambda: m.u8("mainmenu_active") == 1, what="the main menu")
    m.settle()
    m.press("B", pad=pad)
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF, m.text()
    m.press("UP", pad=pad)
    m.settle()
    assert m.selected() != "Test Game.sfc", m.selected()


def test_keypad_in_port_1_drives_the_menu(t):
    m = t.menu(env=NTT1)
    _browse(m, pad=1)
    assert m.psram(PAD1_ID, 1)[0] == PAD_ID_NTT


def test_keypad_in_port_2_drives_the_menu(t):
    m = t.menu(env=NTT2)
    _browse(m, pad=2)
    assert m.psram(PAD1_ID, 1)[0] == 0             # port 1 is a plain pad


def test_keypad_has_no_phantom_presses(t):
    """Idle keypad: its ID nibble must not read as a held button (no auto-repeat, no
    screensaver wake-up, the bar stays where it is)."""
    m = t.menu(env=NTT1)
    m.goto("Test Game.sfc")
    m.step(120)
    assert m.selected() == "Test Game.sfc", m.selected()
    assert m.u16("pad1mem") == 0, hex(m.u16("pad1mem"))


def _play_smw(t, env, config="---\n"):
    m = t.menu(t.sd(config=config,
                    extra={"/Super Mario World.sfc": c.game_rom(SMW, "Super Mario World (USA)")}),
               env=env)
    m.goto("Super Mario World.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="the game card")
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="the ROM boot")
    m.step(900)                                         # past the 10 s hook holdoff
    return m


def test_keypad_gesture_reset_to_menu(t):
    """L+R+Select+X on the keypad in port 1, controller 2 OFF: the FPGA only matches the
    gesture once hx_pad has dropped the keypad's ID nibble."""
    m = _play_smw(t, NTT1)
    m.hold("L", "R", "SEL", "X")
    m.step(30)
    m.release()
    m.wait(lambda: "snes loop cmd=81" in m.fwlog(), frames=300, what="the gesture at the MCU")
    m.wait(lambda: "Super Mario World.sfc" in m.list_names(), frames=1200, what="the menu")


def test_keypad_gesture_with_controller_2_on(t):
    """Same gesture with EnableIngamePad2 on (hx_pad was already patched in): port 1's
    keypad still owns the frame and matches."""
    m = _play_smw(t, NTT1, config="---\nEnableIngamePad2: true\n")
    m.hold("L", "R", "SEL", "X")
    m.step(30)
    m.release()
    m.wait(lambda: "snes loop cmd=81" in m.fwlog(), frames=300, what="the gesture at the MCU")


def test_keypad_drives_the_ingame_menu(t):
    """The in-game menu opened from the keypad answers to it (tab switch with Right) and B
    closes it at once: the close drain must read the idle keypad as idle, not as its ID."""
    m = _play_smw(t, NTT1)
    m.hold(*MENU_COMBO)
    m.step(20)
    m.release()
    m.wait(lambda: m.rgb(12, 10) == TAB_ON, frames=120, what="the in-game menu")
    m.step(30)
    m.press("RIGHT", hold=4, after=10)
    m.wait(lambda: m.rgb(12, 10) != TAB_ON, frames=60, what="the next tab")
    m.press("LEFT", hold=4, after=10)
    m.wait(lambda: m.rgb(12, 10) == TAB_ON, frames=60, what="back on the first tab")
    frame = lambda: m.u8(SMW_FRAME)                     # noqa: E731
    m.press("B", hold=6, after=0)
    f = frame()
    for n in range(240):
        m.step(1)
        if frame() != f:
            break
    assert n < 30, f"the game resumed {n} frames after B"


def test_plain_pad_does_not_patch_the_stub(t):
    """No keypad and controller 2 off: the menu publishes 0 and the gesture still works
    through the untouched stub (the regression guard for everyone else)."""
    m = _play_smw(t, {})
    assert m.psram(PAD1_ID, 1)[0] == 0
    m.hold("L", "R", "SEL", "X")
    m.step(30)
    m.release()
    m.wait(lambda: "snes loop cmd=81" in m.fwlog(), frames=300, what="the gesture at the MCU")
