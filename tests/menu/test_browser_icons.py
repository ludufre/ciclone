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
