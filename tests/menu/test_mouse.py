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


def _hold_right(m, port: int = 1):
    """Right button held alone past MOUSE_RHOLD: Y (the browser's context menu)."""
    m.mouse(right=True, port=port)
    m.step(32)
    m.mouse(port=port)
    m.step(4)


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


def test_right_click_goes_back(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Two Games/")
    m.mouse_click("left")
    m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")
    m.settle()
    _point(m, 200, 30)                            # anywhere: over the logo
    m.mouse_click("right")
    m.wait(lambda: m.list_names() == ROOT, what="a raiz de volta")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF   # no context menu


def test_right_hold_opens_the_context_of_the_row(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    _hold_right(m)
    m.settle()
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), m.text()
    assert m.u16("filesel_sel") == ROOT.index("Test Game.sfc")

def test_right_click_opens_context_and_the_pointer_drives_it(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "Test Game.sfc")
    _hold_right(m)
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
    _hold_right(m)
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
    _hold_right(m)
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
    h = row.find("\u24b7")                        # X shows as the both-buttons glyph
    assert h >= 0, row
    _point(m, 4 * (h + 3) + 1, 212)               # on the label after the glyph
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
    assert (x, y, tile, attr) == (120, 99, 0xFF, 0x31), _oam(m)   # OBJ palette 0
    assert any(m.peek("vram", 0x5FF0 * 2, 32)), "o tile do ponteiro não foi para $5FF0"
    # no cover: OBJ palette 0 is free, the pointer gets black (1) and white (2) of its own
    assert m.peek("cgram", 0x81 * 2, 4) == b"\x00\x00\xff\x7f", m.peek("cgram", 0x81 * 2, 4)
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
    h = row.find("Back")                          # B's label (its key is a mouse glyph)
    assert h >= 0, row
    h -= 4
    assert h >= 0, row
    _point(m, 4 * (h + 4) + 1, 26 * 8 + 4)        # on the label after "B:"
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="voltar ao browser")
    m.settle()
    assert m.list_names() == ROOT


def test_game_info_clip_and_pointer_share_the_palette_without_flicker(t):
    """With a .fmv the pointer and the buttons take the darkest and brightest of each clip
    frame's OBJ palette 7 when the frame's palette goes up (gi_fmv_advance); a mid-tone clip
    is not touched. No other sprite."""
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
    # The test clip's colours are mid tones: the pointer wears the frame's own darkest and
    # brightest and the clip's palette stays exactly the frame's (no black / white forced).
    cg = m.peek("cgram", 168 * 2, 176)
    want = cg[0:2]
    assert all(cg[2 * k:2 * k + 2] == want for k in range(88)), cg.hex()
    # the buttons' halves went up with the arrow, on the same two entries
    tiles = m.peek("vram", 0x5FD0 * 2, 96)
    assert any(tiles[:64]) and any(tiles[64:]), tiles.hex()
    oam = m.peek("oam", 0, 512)
    shown = [i for i in range(128) if oam[4 * i + 1] < 224]
    assert shown == list(range(SLOT, SLOT + 9)), shown   # the arrow + the two buttons


def test_legend_shows_the_mouse_buttons(t):
    """With a mouse in, each one-letter key and its ':' become a two-cell mouse glyph: left
    click for A, right click for B, both for X, right held for Y."""
    m = t.menu(env=MOUSE)
    bar = m.statusbar()
    assert "A:" not in bar and "B:" not in bar, bar
    for lbl, g in (("Select", "\u24c1"), ("Back", "\u24c7"), ("Menu", "\u24b7"),
                   ("Context", "\u24c7\u24bd")):
        assert g + lbl in bar, (lbl, bar)
    m.close()
    m = t.menu()
    assert m.statusbar().startswith(c.tr("text_statusbar_keys")), m.statusbar()

def test_menu_list_scrolls_at_its_edge_rows(t):
    """The standard list edge scroll (mouse_lzone): Favorites with more entries than rows."""
    favs = "".join(f"/Long/game {i:02d}.sfc\n" for i in range(20)).encode()
    m = t.menu(t.sd(extra={**LONG, "/sd2snes/favorites.cfg": favs}), env=MOUSE)
    m.press("SEL", pad=2)
    m.wait(lambda: m.has("game 00"), what="os favoritos")
    m.settle()
    top0 = m.u8("fav_top")
    wy, wh = m.u8("window_y"), m.u8("window_h")
    last = wy + wh - 2                            # the window's last item row
    _point(m, m.u8("window_x") * 4 + 30, 8 * last - 9)
    m.step(90)
    assert m.u8("fav_top") > top0, (top0, m.u8("fav_top"))
    _point(m, m.u8("window_x") * 4 + 30, 8 * (wy + 1) - 9)
    m.wait(lambda: m.u8("fav_top") == 0, frames=900, what="voltar ao topo")


def test_game_info_previous_next_buttons(t):
    m = t.menu(env=MOUSE)
    _point_row(m, "MSU Game/")
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("msugame"), what="a ficha")
    m.mouse_move(2, 0, frames=1, after=4)
    oam = m.peek("oam", 64 * 4, 36)
    shown = [oam[4 * i + 1] < 224 for i in range(9)]
    assert all(shown), oam.hex()
    assert any(m.peek("vram", 0x5FD0 * 2, 64))
    _point(m, 236 + 8, 56 + 8)                    # the next button
    m.mouse_click("left")
    m.wait(lambda: not m.has("msugame"), what="a ficha do próximo jogo")
    assert m.u16("screen_dma_disable") == 1
    _point(m, 4 + 8, 56 + 8)                      # the previous one
    m.mouse_click("left")
    m.wait(lambda: m.has("msugame"), what="a ficha de volta")


YML = "/sd2snes/cheats/TE/Test Game.yml"
CHT = (b'---\n- Name: "First"\n  Enabled: false\n  Code:\n  - "7E1F2A00"\n'
       b'- Name: "Second"\n  Enabled: false\n  Code:\n  - "7E0DBF09"\n')


def _both(m, port: int = 1):
    m.mouse(left=True, right=True, port=port)
    m.step(4)
    m.mouse(port=port)
    m.step(4)


def test_game_info_both_buttons_open_the_cheat_list(t):
    m = t.menu(t.sd(extra={YML: CHT}), env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    footer = m.screen()[26]
    assert "\u24b7Cheats" in footer, footer       # both = Sel here (X keeps its letter)
    _both(m)
    m.wait(lambda: m.has("First"), what="a lista de cheats")


def _cheat_list_mouse(t):
    m = t.menu(t.sd(extra={YML: CHT}), env=MOUSE)
    _point_row(m, "Test Game.sfc")
    _hold_right(m)
    m.settle()
    cheats = c.tr("text_filesel_context_cheats")
    y = m.row_of(cheats)
    _point(m, m.u8("window_x") * 4 + 24, 8 * y - 9)
    m.mouse_click("left")
    m.wait_text("First")
    m.settle()
    return m


def test_cheat_list_both_buttons_add(t):
    m = _cheat_list_mouse(t)
    _both(m)
    m.settle()
    assert m.u8("ce_isnew") == 1
    _both(m)                                      # the editor: both = Sel = add a code
    m.settle()
    assert m.u8("ce_kmode") == 0 and m.has("A B C D E F"), m.text()   # the code keyboard


def test_full_description_scrolls_at_its_edge_rows(t):
    desc = " ".join(f"word{i:03d}" for i in range(260))
    yml = f'---\ntitle: "Long Desc"\ndescription: "{desc}"\n'.encode()
    m = t.menu(t.sd(extra={"/sd2snes/info/TE/Test Game.yml": yml}), env=MOUSE)
    _point_row(m, "Test Game.sfc")
    m.mouse_click("left")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Long Desc"), what="a ficha")
    m.settle()
    _hold_right(m)                                # Y: the full description
    m.wait(lambda: m.u8("gi_desc_full") == 1, what="a descrição completa")
    m.settle()
    assert m.u16("gi_desc_scroll") == 0
    _point(m, 100, 24 * 8 + 4)                    # its last row
    m.step(90)
    assert m.u16("gi_desc_scroll") > 0, m.u16("gi_desc_scroll")
    _point(m, 100, 17 * 8 + 4)                    # its first row
    m.wait(lambda: m.u16("gi_desc_scroll") == 0, frames=900, what="voltar ao topo")


def _to_option(m, *labels):
    for _ in range(10):
        m.press("X", pad=2)
        m.settle()
        if m.has(c.tr(labels[0])):
            break
    for i, lbl in enumerate(labels):
        want = c.tr(lbl)
        for _ in range(30):
            if want in m.bar_row():
                break
            m.press("DOWN", pad=2)
            m.step(8)
        assert want in m.bar_row(), (lbl, m.text())
        if i < len(labels) - 1:
            m.press("A", pad=2)
            m.settle()


def test_click_on_an_option_sets_the_next_value(t):
    m = t.menu(env=MOUSE)
    _to_option(m, "mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_hide_ext")
    cfg = 0xFF0118
    v0 = m.psram(cfg, 1)[0]
    row = m.u8("bar_yl") + 1
    _point(m, m.u8("window_x") * 4 + 24, 8 * row - 9)
    m.mouse_click("left")
    m.wait(lambda: m.psram(cfg, 1)[0] != v0, frames=300, what="o valor seguinte")
    v1 = m.psram(cfg, 1)[0]
    m.settle()
    m.mouse_click("left")                         # past the last value: back to the first
    m.wait(lambda: m.psram(cfg, 1)[0] != v1, frames=300, what="a volta ao primeiro")
    assert m.psram(cfg, 1)[0] == v0


def test_click_past_the_last_value_jumps_to_the_first(t):
    """A click on the last value goes straight back to the first one: the dialog must not
    walk down through every value in between (it used to, one per frame, on screen)."""
    m = t.menu(env=MOUSE)
    _to_option(m, "mtext_mm_cfg", "mtext_cfg_ingame", "mtext_ingame_shortreset")
    cfg = 0xFF0100 + 0x9F
    assert m.psram(cfg, 1)[0] == 3                # ROM (the default)
    row = m.u8("bar_yl") + 1
    _point(m, m.u8("window_x") * 4 + 24, 8 * row - 9)
    m.mouse_click("left")
    m.wait(lambda: m.psram(cfg, 1)[0] == 4, frames=300, what="Duração")
    m.settle()
    between = [c.encode_menu_text(c.tr(k)) for k in ("text_nav_rom", "text_nav_folder")]
    m.mouse_click("left", hold=3, after=1)
    seen = []
    for _ in range(120):
        m.step(1)
        line = m.screen()[row]
        seen += [k for k in between if k in line]
        if m.psram(cfg, 1)[0] == 0:
            break
    assert m.psram(cfg, 1)[0] == 0, m.psram(cfg, 1)[0]
    assert not seen, seen


def test_pointer_moves_in_a_value_dialog(t):
    m = t.menu(env=MOUSE)
    _to_option(m, "mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_hide_ext")
    m.press("A", pad=2)                           # the option's value dialog
    m.wait(lambda: m.u8("mouse_mode") == 5, frames=120, what="o diálogo de valor")
    _point(m, 60, 60, after=4)
    assert _oam(m)[:2] == (60, 59), _oam(m)


def test_cheat_keyboard_click_types_the_clicked_key(t):
    m = _cheat_list_mouse(t)
    _both(m)                                      # a new cheat
    m.settle()
    _both(m)                                      # add a code: the hex keyboard
    m.settle()
    assert m.u8("ce_kmode") == 0
    _point(m, 4 * 14 + 1, 8 * 17 - 9)             # row 1 ("A B C D E F -"), key B
    assert (m.u8("ce_krow"), m.u8("ce_kcol")) == (1, 1)  # the cursor followed the pointer
    m.step(4)
    assert _oam(m)[:2] == (4 * 14 + 1, 8 * 17 - 10), _oam(m)  # and so did the sprite
    m.mouse_click("left")
    m.settle(stable=6)
    assert m.has("B_"), m.text()
    _point(m, 4 * 20 + 1, 8 * 16 - 9)             # row 0, key 4
    m.mouse_click("left")
    m.settle(stable=6)
    assert m.has("B4_"), m.text()


def test_cheat_keyboard_right_click_deletes_and_held_right_cancels(t):
    m = _cheat_list_mouse(t)
    _both(m)                                      # a new cheat
    m.settle()
    _both(m)                                      # add a code: the hex keyboard
    m.settle()
    _point(m, 4 * 14 + 1, 8 * 17 - 9)             # key B
    m.mouse_click("left")
    m.settle(stable=6)
    m.mouse_click("left")
    m.settle(stable=6)
    assert m.has("BB_"), m.text()
    m.mouse_click("right")                        # a right click: Del
    m.settle(stable=6)
    assert m.has("B_") and not m.has("BB_"), m.text()
    assert m.u8("ce_kmode") == 0 and m.has("A B C D E F"), m.text()  # still on the keyboard
    _hold_right(m)                                # held: Cancel
    m.settle(stable=6)
    assert not m.has("A B C D E F"), m.text()


def test_cheat_name_keyboard_follows_types_deletes_and_cancels(t):
    m = _cheat_list_mouse(t)
    _hold_right(m)                                # edit "First"
    m.settle()
    m.press("A", pad=2)                           # the name: the letters keyboard
    m.settle()
    assert m.u8("ce_kmode") == 1
    _point(m, 4 * 36 + 1, 8 * 16 - 9, after=4)    # row 1 ("N O ... Z"), key Z
    assert _oam(m)[:2] == (4 * 36 + 1, 8 * 16 - 10), _oam(m)
    m.mouse_click("left")
    m.settle(stable=6)
    assert m.has("FirstZ_"), m.text()
    m.mouse_click("right")                        # Del
    m.settle(stable=6)
    assert m.has("First_") and m.has("N O P Q"), m.text()
    _hold_right(m)                                # Cancel
    m.settle(stable=6)
    assert not m.has("N O P Q") and m.has("First"), m.text()


def test_menu_bar_jumps_to_the_pointer(t):
    m = t.menu(env=MOUSE)
    m.press("X", pad=2)                           # the main menu
    m.settle()
    wy, wh = m.u8("window_y"), m.u8("window_h")
    _point(m, m.u8("window_x") * 4 + 30, 8 * (wy + 1) - 9)
    m.settle(stable=6)
    assert m.u8("listsel_sel") == 0
    seen = []
    m.mouse(0, 4 * (wh - 3))                      # one move (doubled) to the last item
    for _ in range(14):
        m.step(1)
        seen.append(m.u8("listsel_sel"))
    assert seen[-1] == m.u8("listsel_max") - 1, seen
    assert len(set(seen)) <= 3, seen              # 0, last-1, last: no walk


def test_language_change_keeps_the_bar_on_the_pointer(t):
    """Changing the language by a click reopens the main menu with its bar on the first row;
    the pointer rests on the last row (the Language entry), which is also the list's edge
    zone. The bar must go straight back to the pointer, not walk down (the edge zone used to
    step it down row by row)."""
    m = t.menu(env=MOUSE)
    m.press("X", pad=2)
    m.settle()
    wy, wh = m.u8("window_y"), m.u8("window_h")
    last = wy + wh - 2
    _point(m, m.u8("window_x") * 4 + 30, 8 * last - 9)
    m.settle(stable=6)
    lang = m.u8("cur_lang")
    m.mouse_click("left", hold=3, after=1)
    bars = []
    for _ in range(80):
        m.step(1)
        bars.append(m.u8("bar_yl"))
    assert m.u8("cur_lang") != lang
    assert bars[-1] == last - 1, bars
    walk = [b for b in bars if wy < b < last - 1]
    assert len(walk) <= 2, bars                   # first row once at most, then the pointer's
