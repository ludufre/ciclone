"""Info screen on a crowded info bucket: the firmware indexes the bucket once (src/dirindex.c) and
every sidecar of the next game in it is opened without scanning the directory.

On a real card /sd2snes/info/SU holds every "Super ..." game, 2000+ files: FAT finds a name by
reading the directory from the top, the info screen opens five or six sidecars per game plus
a pass for its guides, and an Up/Down there read ~3500 sectors (over a second on a Mk.III).
How slow depended on where the game's files had been written in the directory."""
import gzip
import sys
from pathlib import Path

import ciclone as c
from test_pcm_player import _fmv
from test_qoa_clip import _long_qoa

sys.path.insert(0, str(c.ROOT / "tools"))
from sd_fixtures import lorom  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
MAN_META = 0xFF0760          # +0 bit0 a guide is present, +1 how many
BUCKET = "/sd2snes/info/SU/"
GAMES = (("Super Alpha", "Alpha Clip"), ("Super Beta", "Beta Clip"), ("Super Gamma", "Gamma Clip"))
FILLERS = 1500


def _card(t):
    extra = {}
    for i in range(FILLERS):     # written first: the games' sidecars end up at the end of the directory
        extra[f"{BUCKET}Super filler {i:04d}.yml"] = b""
    for stem, title in GAMES:
        extra[f"/Supers/{stem}.sfc"] = lorom(stem.upper())
        extra[f"{BUCKET}{stem}.yml"] = f'---\ntitle: "{title}"\nfmv: true\n'.encode()
        extra[f"{BUCKET}{stem}.fmv"] = _fmv(24)
        extra[f"{BUCKET}{stem}.qoa"] = _long_qoa(2)
    extra[f"{BUCKET}Super Beta.man"] = gzip.decompress((FIX / "probe.man.gz").read_bytes())
    sd = t.sd(extra=extra)
    m = t.menu(sd)
    m.goto("Supers/")
    m.press("A")
    m.wait(lambda: m.has("Super Alpha.sfc"), what="the folder")
    m.settle()
    return sd, m


def _builds(m):
    return [ln for ln in m.fwlog().splitlines() if ln.startswith("dirindex: ")]


def test_up_down_in_a_crowded_bucket_does_not_scan_it(t):
    sd, m = _card(t)
    m.goto("Super Alpha.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Alpha Clip"), what="the first screen")
    m.settle()
    before = m.sdstat()[0]
    m.press("DOWN")
    m.wait(lambda: m.has("Beta Clip"), frames=1200, what="the next game's screen")
    read = m.sdstat()[0] - before
    t.log("sectors for one Up/Down:", read)
    # the sidecars' own data (the .yml, the .fmv's first frames, the start of the .qoa, the
    # guide's header) is ~160 sectors; one scan of the bucket alone is ~280, and the screen used
    # to make enough of them to read ~4900
    assert read < 250, f"{read} sectors for one Up/Down"
    builds = _builds(m)
    assert len(builds) == 1 and f"{FILLERS + 10} files" in builds[0], builds
    meta = m.psram(MAN_META, 2)
    assert meta[0] & 1 and meta[1] == 1, f"the guide was not found (meta {meta.hex()})"
    m.wait(lambda: m.fwlog().count("qoa: kick") >= 2, frames=600, what="its clip playing")
    m.settle()
    m.press("DOWN")
    m.wait(lambda: m.has("Gamma Clip"), frames=1200, what="the third game's screen")
    m.settle()
    meta = m.psram(MAN_META, 2)
    assert not meta[0] & 1, "a guide that does not exist"
    m.close()


def test_a_write_to_the_card_drops_the_index(t):
    """The index only answers while nothing has written to the card: deleting a ROM takes its
    sidecars out of the bucket, and the next screen indexes it again."""
    sd, m = _card(t)
    m.goto("Super Alpha.sfc")
    m.press("A")
    m.wait(lambda: m.has("Alpha Clip"), what="the first screen")
    m.settle()
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="back in the browser")
    m.settle()
    m.goto("Super Beta.sfc")
    m.press("Y")
    m.settle()
    for _ in range(30):                            # Delete is the menu's last row
        if c.tr("text_filesel_context_delete_file") in m.bar_row():
            break
        m.press("DOWN")
        m.settle(stable=6)
    m.press("A")
    m.wait_text(c.tr("text_confirm_delete_file"), frames=300)
    m.press("LEFT")                                # default = No; Yes is on the left
    m.settle(stable=6)
    m.press("A")
    m.wait(lambda: "Super Beta.sfc" not in m.list_names(), what="the ROM gone from the list")
    m.settle()
    m.goto("Super Gamma.sfc")
    m.press("A")
    m.wait(lambda: m.has("Gamma Clip"), what="the third game's screen")
    m.settle()
    builds = _builds(m)
    assert len(builds) == 2 and f"{FILLERS + 6} files" in builds[1], builds
    m.close()
    left = t.listdir(sd, BUCKET.rstrip("/"))
    assert not [n for n in left if n.startswith("Super Beta.")], "the sidecars stayed"
