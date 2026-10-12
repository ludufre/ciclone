"""O browser desenha um icone por tipo antes de cada nome (snes/diricon.a65): dois glifos da
fonte (utils/fontedit.py BROWSER_ICONS) na coluna do cursor, numa paleta por tipo. Pasta que
abre como seu jogo MSU-1 mostra o controle de SNES em amarelo no lugar da pasta."""
import sys

import ciclone as c

sys.path.insert(0, str(c.ROOT / "tools"))
import sd_fixtures as fx  # noqa: E402

sys.path.insert(0, str(c.SD2SNES / "snes" / "utils"))
import fontedit  # noqa: E402
sys.path.pop(0)

ICON = {name: code for name, (code, _) in fontedit.BROWSER_ICONS.items()}
COL = 2   # cursor_x of the browser

FILES = {
    "/Classic Racer.smc": fx.lorom("CLASSIC RACER"),
    "/Plumber Bros.nes": b"NES\x1a" + bytes(16 * 1024 + 12),
    "/Hedgehog Run.sms": bytes(32 * 1024),
    "/Pocket Puzzle.gb": bytes(32 * 1024),
    "/Pocket Color.gbc": bytes(32 * 1024),
    "/Stick Fighter.a26": bytes(4096),
    "/Overworld Theme.spc": bytes(66048),
    "/Blue Night.thm": b"FXTHEME1" + bytes(64),
}

# name on screen -> (icon, print palette)
WANT = {
    "MSU Game/": ("snes", 1),           # opens as its MSU-1 game: a game, in the folders' yellow
    "Two Games/": ("folder", 1),
    "Empty Folder/": ("folder", 1),
    "Test Game.sfc": ("snes", 0),
    "Classic Racer.smc": ("snes", 0),
    "Plumber Bros.nes": ("nes", 6),
    "Hedgehog Run.sms": ("sms", 3),
    "Pocket Puzzle.gb": ("gb", 6),
    "Pocket Color.gbc": ("gb", 3),
    "Stick Fighter.a26": ("a26", 1),
    "Overworld Theme.spc": ("spc", 2),
    "Blue Night.thm": ("theme", 0),
}


def _icons(m):
    got = {}
    for name in WANT:
        y = m.row_of(name)
        assert y is not None, (name, m.text())
        code, pal = m.tile_at(COL, y)
        right, _ = m.tile_at(COL + 1, y)
        assert right == code + 1, (name, code, right)
        got[name] = (code, pal)
    return got


def test_browser_icons_per_type(t):
    m = t.menu(t.sd(extra=FILES))
    m.wait(lambda: m.has("Stick Fighter.a26"), what="a lista")
    m.settle()
    got = _icons(m)
    for name, (icon, pal) in WANT.items():
        assert got[name] == (ICON[icon], pal), (name, got[name], (ICON[icon], pal))


def test_msu_folder_icon_follows_the_option(t):
    """With OpenMsuFolders off the folder is a folder: nothing is probed."""
    m = t.menu(t.sd(config="---\nOpenMsuFolders: false\n"))
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    y = m.row_of("MSU Game/")
    assert m.tile_at(COL, y) == (ICON["folder"], 1), m.tile_at(COL, y)


def test_msu_folder_keeps_the_plain_dir_mark(t):
    """The firmware marks a folder that opens as its game inside the entry's size string. The
    size column still has to read like any other folder's."""
    m = t.menu(t.sd())
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    rows = {name: m.screen()[m.row_of(name)].rstrip() for name in ("MSU Game/", "Two Games/")}
    for name, row in rows.items():
        assert row.endswith(" <dir>"), (name, row)


def _plain(m, name, col):
    """The name's own glyphs (ASCII) from column col on."""
    y = m.row_of(name)
    assert y is not None, (name, m.text())
    return [m.tile_at(col + i, y)[0] for i in range(len(name))] == [ord(ch) for ch in name]


def test_icons_off_names_start_in_the_icon_column(t):
    """BrowserIcons: false -> no icon, and the name starts where the icon was (as before 2.17)."""
    m = t.menu(t.sd(extra=FILES, config="---\nBrowserIcons: false\n"))
    m.wait(lambda: m.has("Stick Fighter.a26"), what="a lista")
    m.settle()
    icons = {code for code in ICON.values()} | {code + 1 for code in ICON.values()}
    for name in WANT:
        assert _plain(m, name, COL), (name, [m.tile_at(COL + i, m.row_of(name)) for i in range(4)])
        assert m.tile_at(COL, m.row_of(name))[0] not in icons, name


def _set_icons(m, on):
    """X > Settings > Browser options > "File type icons" -> On/Off, back to the browser."""
    m.press("X")
    for key in ("mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_icons"):
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
    want = c.encode_menu_text(c.tr("text_on" if on else "text_off"))
    for _ in range(4):                             # kv_onoff is Off, On: UP goes forward,
        if want in m.bar_row():                    # DOWN back, no wrap
            break
        m.press("UP" if on else "DOWN")
        m.step(10)
    assert want in m.bar_row(), m.text()
    m.press("A")
    m.settle()
    for _ in range(3):                             # browser options, settings, main menu
        m.press("B")
        m.settle()


def test_icons_toggle_in_the_menu(t):
    """Switching the option repaints the list at once. Back on, the blank between the icon and
    the name is redrawn too: before it, that cell held the name's third letter."""
    m = t.menu(t.sd(extra=FILES))
    m.wait(lambda: m.has("Stick Fighter.a26"), what="a lista")
    m.settle()
    _set_icons(m, False)
    assert _plain(m, "Classic Racer.smc", COL), m.text()
    _set_icons(m, True)
    y = m.row_of("Classic Racer.smc")
    assert m.tile_at(COL, y) == (ICON["snes"], 0), m.tile_at(COL, y)
    assert m.tile_at(COL + 2, y)[0] == 32, m.tile_at(COL + 2, y)
    assert _plain(m, "Classic Racer.smc", COL + 3), m.text()
