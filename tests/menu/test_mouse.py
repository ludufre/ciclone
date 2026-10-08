"""SNES Mouse in the menu (snes/mouse.a65): a pointer sprite in the file browser and a
translator (left = A, right = B, vertical motion = Up/Down) everywhere else.

Geometry: browser entry i sits on text row 9+i, shown on screen lines 59+8i..66+8i (the
list scrolls by 13 lines); the status bar is text row 28 (lines 209..216). Text half-column
h is OBJ pixels 4h..4h+3."""
import ciclone as c

ROOT = ["Empty Folder/", "MSU Game/", "Two Games/", "Test Game.sfc"]
MOUSE = {"CICLONE_PORT1": "mouse"}
SLOT = 64


def _row_y(i: int) -> int:
    return 62 + 8 * i


def _point(m, x: int, y: int, port: int = 1, after: int = 2):
    """Puts the pointer on (x, y). The menu doubles a frame's motion from 4 counts up, and a
    frame whose latch nobody read loses its motion, so this steers by what the menu shows."""
    for _ in range(40):
        dx, dy = x - m.u16("mouse_x"), y - m.u16("mouse_y")
        if dx == 0 and dy == 0:
            m.step(after)
            return

        def part(d):
            if abs(d) >= 8:
                return max(-127, min(127, d // 2 if d > 0 else -((-d) // 2)))
            return max(-3, min(3, d))
        m.mouse(part(dx), part(dy), port=port)
        m.step(2)                                 # the motion shows up one frame late
    raise c.MenuError(f"o ponteiro não chegou a ({x},{y}): está em "
                      f"({m.u16('mouse_x')},{m.u16('mouse_y')})")


def _oam(m) -> tuple[int, int, int, int]:
    return tuple(m.peek("oam", SLOT * 4, 4))


def _point_row(m, name: str, port: int = 1):
    i = m.list_names().index(name)
    _point(m, 40, _row_y(i), port=port)
    m.settle(stable=6)


def test_no_mouse_no_pointer(t):
    m = t.menu()
    m.press("DOWN")
    m.settle()
    assert m.u8("mouse_ptr_on") == 0
    assert _oam(m)[1] >= 0xE0, _oam(m)


def test_pointer_follows_the_mouse(t):
    m = t.menu(env=MOUSE)
    _point(m, 100, 150, after=4)
    x, y, tile, attr = _oam(m)
    assert (x, y) == (100, 149), (x, y)          # an OBJ shows one line below its Y
    assert tile == 0 and attr == 0x3F, (tile, attr)
    assert m.peek("oam", 512 + SLOT // 4, 1)[0] & 0x03 == 0   # small, X bit 8 clear
    # the arrow's tile went up to VRAM $3000 and is not blank
    assert any(m.peek("vram", 0x3000 * 2, 32)), m.peek("vram", 0x3000 * 2, 32)


def test_hover_moves_the_bar(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    assert m.selected() == "Test Game.sfc", m.selected()
    _point_row(m, "MSU Game/")
    assert m.selected() == "MSU Game/", m.selected()


def test_still_mouse_leaves_the_pad_alone(t):
    """A mouse at rest must not pull the bar back to the row under the pointer."""
    m = t.menu(env=MOUSE)
    _point_row(m, "Empty Folder/")
    m.press("DOWN", pad=2)
    m.settle()
    m.press("DOWN", pad=2)
    m.settle()
    assert m.selected() == "Two Games/", m.selected()


def test_left_click_enters_folder_and_parent_returns(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Two Games/")
    m.mouse_click("left")
    m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")
    m.settle()
    assert m.list_names()[0].startswith(".."), m.list_names()
    _point(m, 40, _row_y(0))
    m.mouse_click("left")
    m.wait(lambda: m.list_names() == ROOT, what="a raiz de volta")
    m.settle()
    assert m.selected() == "Two Games/"


def test_no_stray_motion_after_a_folder_change(t):
    """A read of the mouse's motion bits that crossed the auto-read at line 225 left the
    register misaligned: the next frame read a few bits late and showed motion nobody made,
    and the bar jumped to the pointer's row after "..". Repeated: it hit 1 in 5."""
    for _ in range(5):
        m = t.menu(env=MOUSE)
        _point_row(m, "Two Games/")
        m.mouse_click("left")
        m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")
        m.settle()
        _point(m, 40, _row_y(0))
        m.mouse_click("left")
        m.wait(lambda: m.list_names() == ROOT, what="a raiz de volta")
        m.settle()
        assert m.selected() == "Two Games/", m.selected()
        assert m.u16("mouse_x") == 40, m.u16("mouse_x")
        m.close()


def test_click_on_another_row_selects_it_first(t):
    """A click lands on the row under the pointer even when the bar is elsewhere."""
    m = t.menu(env=MOUSE)
    _point_row(m, "Two Games/")
    m.press("UP", pad=2)                          # the bar leaves the pointer's row
    m.settle()
    assert m.selected() == "MSU Game/"
    m.mouse_click("left")
    m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")


def test_right_hold_goes_back(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Two Games/")
    m.mouse_click("left")
    m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")
    m.settle()
    _point(m, 200, 30)                            # anywhere: over the logo
    m.mouse_click("right", hold=40, after=4)
    m.wait(lambda: m.list_names() == ROOT, what="a raiz de volta")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF   # no context menu on the release


def test_right_click_opens_context_and_the_pointer_drives_it(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("right")
    m.settle()
    fav = c.tr("text_filesel_context_add_to_favorites")
    assert m.has(fav), m.text()
    assert _oam(m)[1] < 0xE0, "o ponteiro sumiu no menu de contexto"
    bar = m.bar_row()
    assert fav in bar, bar
    y = m.row_of(fav)
    _point(m, m.u8("window_x") * 4 + 24, 8 * (y + 1) - 9)   # the row below "Add to favorites"
    m.settle(stable=6)
    assert m.bar_row() != bar, (bar, m.bar_row())
    sel = m.bar_row()
    m.mouse_move(0, 0, frames=1, after=10)
    assert m.bar_row() == sel                     # a still pointer leaves the bar alone


def test_right_click_closes_the_menu_and_nothing_else(t):
    """The right click that closes a menu must not reach the browser: on the console it put
    the bar on the pointer's row and opened the context menu again (fixed: a mode change
    starts with no edge)."""
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("right")
    m.settle()
    fav = c.tr("text_filesel_context_add_to_favorites")
    assert m.has(fav), m.text()
    _point(m, 120, 70)                            # the pointer wanders off over the list
    m.mouse_click("right", hold=6, after=2)
    for _ in range(30):
        m.step(2)
        assert not m.has(fav), "o menu de contexto reabriu\n" + m.text()
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF
    assert m.selected() == "Test Game.sfc", m.selected()


def test_left_click_on_a_menu_row_runs_it(t):
    sd = t.sd()
    m = t.menu(sd, env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("right")
    m.settle()
    fav = c.tr("text_filesel_context_add_to_favorites")
    y = m.row_of(fav)
    m.press("DOWN", pad=2)                        # the bar leaves "Add to favorites"
    m.settle(stable=6)
    _point(m, m.u8("window_x") * 4 + 24, 8 * y - 9)
    m.mouse_click("left")
    m.settle()
    assert not m.has(fav), m.text()
    m.close()
    got = t.read(sd, "/sd2snes/favorites.cfg")
    assert got is not None and b"/Test Game.sfc" in got, got


def test_game_info_ignores_motion_and_drags_to_the_next_game(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    before = m.text()
    m.mouse_move(0, -60, frames=10, after=20)     # no button: nothing happens
    assert m.u16("screen_dma_disable") == 1 and m.text() == before
    m.mouse(left=True)                            # drag down = previous game
    m.step(2)
    m.mouse_move(0, 40, frames=8, left=True)
    m.mouse()
    m.wait(lambda: m.has("msugame"), what="a ficha do jogo anterior")
    assert m.u16("screen_dma_disable") == 1


def test_legend_click_presses_its_key(t):
    m = t.menu(env=MOUSE)
    row = m.screen()[28]
    h = row.find("X:")
    assert h >= 0, row
    _point(m, 4 * (h + 3) + 1, 212)               # on the 'n' of "Menu"
    m.mouse_click("left")
    m.wait(lambda: m.u8("mainmenu_active") == 1, what="o menu principal")
    m.settle()
    assert m.u16("window_stack_head") != 0xFFFF


def test_mouse_in_port_2(t):
    m = t.menu(env={"CICLONE_PORT2": "mouse"})
    _point_row(m, "Test Game.sfc", port=2)
    assert m.selected() == "Test Game.sfc", m.selected()
    assert m.u16("mouse_x") == 40


def test_pad_still_works_with_a_mouse_in_port_1(t):
    m = t.menu(env=MOUSE)
    m.press("DOWN", pad=2)
    m.settle()
    assert m.selected() == "MSU Game/", m.selected()


def test_pointer_follows_into_game_info_and_back(t):
    """Game info draws its own pointer (tile $1FF at VRAM $5FF0); back in the browser the
    browser's (tile 0 at $3000) is rebuilt."""
    m = t.menu(env=MOUSE)
    _point_row(m, "MSU Game/")
    assert _oam(m)[2] == 0x00
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("msugame"), what="a ficha")
    m.mouse_move(2, 0, frames=1, after=4)
    assert _oam(m)[2] == 0xFF and _oam(m)[1] < 0xE0, _oam(m)
    m.mouse_click("right")                        # translator: B back to the browser
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="sair da ficha")
    m.settle()
    m.mouse_move(1, 0, frames=1, after=4)
    assert _oam(m)[1] < 0xE0 and _oam(m)[2] == 0x00, _oam(m)
    assert any(m.peek("vram", 0x3000 * 2, 32))
    assert m.list_names() == ROOT, m.list_names()


def test_click_acts_on_release(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Two Games/")
    m.mouse(left=True)
    m.step(20)
    assert m.list_names() == ROOT, "o clique agiu antes de soltar"
    m.mouse()
    m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")


def test_both_buttons_open_the_main_menu(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse(left=True)
    m.step(3)
    m.mouse(left=True, right=True)               # the second button joins a bit later
    m.step(4)
    m.mouse(right=True)                          # and they come up apart
    m.step(2)
    m.mouse()
    m.wait(lambda: m.u8("mainmenu_active") == 1, what="o menu principal")
    m.settle()
    assert not m.has(c.tr("text_filesel_context_add_to_favorites")), m.text()
    assert m.list_names() == ROOT or m.u16("window_stack_head") != 0xFFFF


def test_pointer_is_black_and_white(t):
    m = t.menu(env=MOUSE)
    _point(m, 100, 150, after=6)
    o, b = m.u8("mouse_cgo"), m.u8("mouse_cgb")
    cg = m.peek("cgram", (0xF0 + o) * 2, 2), m.peek("cgram", (0xF0 + b) * 2, 2)
    assert cg == (b"\x00\x00", b"\xff\x7f"), (o, b, cg)


LONG = {f"/Long/game {i:02d}.sfc": b"\0" * 0x8000 for i in range(40)}


def _long(t):
    m = t.menu(t.sd(extra=LONG), env=MOUSE)
    m.goto("Long/", pad=2)                        # the mouse owns port 1
    m.press("A", pad=2)
    m.wait(lambda: "game 00.sfc" in m.list_names(), what="a pasta Long/")
    m.settle()
    return m


def test_bar_jumps_to_the_pointer(t):
    """No walk down the list: one d-pad step from the old row, then a jump next to the
    pointer's row and the last step."""
    m = _long(t)
    _point(m, 40, 30)                             # over the logo: no entry under it
    m.settle(stable=6)
    assert m.u16("filesel_sel") == 0
    seen = []
    m.mouse(0, 60)                                # one move: row 0 -> about row 13
    for _ in range(12):
        m.step(1)
        seen.append(m.u16("filesel_sel"))
    target = m.u8("mouse_hrow")
    assert seen[-1] == target and target >= 10, (target, seen)
    assert len(set(seen)) <= 4, seen              # 0, 1, target-1, target


def test_resting_on_the_edge_rows_scrolls(t):
    m = _long(t)
    first = m.list_names()[0]
    _point(m, 40, _row_y(17))                     # the last row on screen
    m.step(80)
    names = m.list_names()
    assert names[0] != first, names
    assert m.u16("filesel_sel") == m.u16("listdisp") - 1
    _point(m, 40, 120)                            # back to the middle: it stops
    m.settle(stable=8)
    stop = m.list_names()[0]
    m.step(40)
    assert m.list_names()[0] == stop
    _point(m, 40, _row_y(0))                      # the first row
    m.wait(lambda: m.list_names()[0] == first, frames=900, what="voltar ao topo")
    assert m.u16("filesel_sel") == 0


def test_edge_row_click_still_opens(t):
    """A click on the last row before the scroll starts opens that row."""
    m = _long(t)
    _point(m, 40, _row_y(17))
    name = m.list_names()[17]
    m.mouse_click("left", hold=2, after=2)
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha de " + name)


def test_short_list_edge_rows_are_plain(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")                # the last entry: nothing to scroll
    m.step(60)
    assert m.list_names() == ROOT and m.selected() == "Test Game.sfc"


def _ficha(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    return m


def test_game_info_shows_the_pointer_and_hides_it_when_idle(t):
    m = _ficha(t)
    _point(m, 120, 100, after=3)
    x, y, tile, attr = _oam(m)
    assert (x, y, tile, attr) == (120, 99, 0xFF, 0x3F), _oam(m)
    assert any(m.peek("vram", 0x5FF0 * 2, 32)), "o tile do ponteiro não foi para $5FF0"
    assert m.peek("cgram", 0xF1 * 2, 4) == b"\x00\x00\xff\x7f", m.peek("cgram", 0xF1 * 2, 4)
    assert all(m.peek("oam", i * 4 + 1, 1)[0] >= 0xE0 for i in range(64)), "sobrou sprite da capa"
    m.step(150)
    assert _oam(m)[1] >= 0xE0, _oam(m)


def test_game_info_description_click_opens_the_full_text(t):
    m = _ficha(t)
    _point(m, 100, 23 * 8 + 4)
    m.mouse_click("left")
    m.wait(lambda: m.u8("gi_desc_full") == 1, what="a descrição em tela cheia")
    assert m.u16("screen_dma_disable") == 1


def test_game_info_footer_click_presses_its_key(t):
    m = _ficha(t)
    row = m.screen()[26]
    h = row.find("B:")
    assert h >= 0, row
    _point(m, 4 * (h + 4) + 1, 26 * 8 + 4)        # on the label after "B:"
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="voltar ao browser")
    m.settle()
    assert m.list_names() == ROOT


def test_game_info_clip_and_pointer_share_the_palette_without_flicker(t):
    """With a .fmv the pointer takes the darkest and brightest of each clip frame's OBJ
    palette 7 when the frame's palette goes up (gi_fmv_advance), so the clip never flips
    between two palettes; the rest of the palette is the frame's own. No other sprite."""
    from test_pcm_player import _fmv, PCM
    sd = t.sd(extra={"/sd2snes/info/TE/Test Game.yml": b'---\ntitle: "Clip Probe"\nfmv: true\n',
                     "/sd2snes/info/TE/Test Game.fmv": _fmv(8),
                     "/sd2snes/info/TE/Test Game.pcm": PCM})
    m = t.menu(sd, env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Clip Probe"), what="a ficha")
    for i in range(30):                           # keep the pointer up past a few clip frames
        m.mouse(1 if i % 2 else -1, 0)
        m.step(1)
    o, b = m.u8("mouse_cgo"), m.u8("mouse_cgb")
    assert o != b and m.u8("mouse_fsetup") == 1, (o, b)
    # Sampled at the frame boundary the emulator may stop inside the clip's upload window,
    # between its palette DMA and mouse_fmv_pal; outside it the palette is the frame's own
    # with exactly the pointer's two entries black and white.
    for _ in range(20):
        cg = m.peek("cgram", 168 * 2, 176)
        if cg[2 * (72 + o):2 * (72 + o) + 2] == b"\x00\x00":
            break
        m.mouse(1, 0)
        m.step(1)
    want = cg[0:2]                                # the test clip: one colour per frame
    for k in range(88):
        got = cg[2 * k:2 * k + 2]
        if k == 72 + o:
            assert got == b"\x00\x00", (k, got)
        elif k == 72 + b:
            assert got == b"\xff\x7f", (k, got)
        else:
            assert got == want, (k, got, want)
    oam = m.peek("oam", 0, 512)
    shown = [i for i in range(128) if oam[4 * i + 1] < 224]
    assert shown == [SLOT], shown
