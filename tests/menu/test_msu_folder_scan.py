"""Opening a folder that holds many MSU-1 games, each in its own folder (one ROM, the .msu and
dozens of .pcm tracks). The browser shows each such folder as a game, and telling one takes a
walk through it: walking every subfolder at listing time, each opened by path, cost seconds.
Only the folders on the page being drawn are walked now, each opened by its start cluster.
These measure the card reads against the same listing with OpenMsuFolders off, on a card
shaped like a real one (FAT32, 32 KB clusters). The files are empty: listing a folder only
reads directory entries."""
import sys

import ciclone as c

sys.path.insert(0, str(c.SD2SNES / "snes" / "utils"))
import fontedit  # noqa: E402
sys.path.pop(0)

ICON_SNES = fontedit.BROWSER_ICONS["snes"][0]
ICON_FOLDER = fontedit.BROWSER_ICONS["folder"][0]

TRACKS = 40
COLLECTION = "MSU Collection"


def _collection(games: int) -> dict:
    files = {}
    for g in range(1, games + 1):
        name = f"Quest Saga {g:03d} (MSU-1)"
        stem = f"quest_saga_{g:03d}_msu1"
        d = f"/{COLLECTION}/{name}"
        files[f"{d}/{stem}.sfc"] = b""
        files[f"{d}/{stem}.msu"] = b""
        for k in range(1, TRACKS + 1):
            files[f"{d}/{stem}-{k}.pcm"] = b""
    return files


def _open_collection(t, games: int, probe: bool) -> tuple[int, int]:
    """Card sectors read (and stream restarts) by the READDIR of the collection folder."""
    cfg = f"---\nOpenMsuFolders: {'true' if probe else 'false'}\n"
    m = t.menu(t.sd(config=cfg, extra=_collection(games), size_mb=2200, cluster=64))
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    m.goto(f"{COLLECTION}/")
    before = m.sdstat()
    m.press("A")
    m.wait(lambda: m.has("Quest Saga 001 (MSU-1)/"), frames=20000, every=10, what="a coleção")
    m.settle()                  # the page's MSU-1 icons are settled after the listing
    after = m.sdstat()
    if probe:
        y = m.row_of("Quest Saga 001 (MSU-1)/")
        assert m.tile_at(2, y)[0] == ICON_SNES, (m.tile_at(2, y), m.text())
    m.close()
    sectors, restarts = after[0] - before[0], after[1] - before[1]
    t.log(f"{games} jogos, OpenMsuFolders {probe}: {sectors} setores, {restarts} reinícios")
    return sectors, restarts


def test_msu_collection_listing_grows_linearly(t):
    """What the MSU-1 folder probe adds to a listing has to grow with the number of
    subfolders, not with its square: each subfolder may be read, the folder being listed
    must not be read again for every one of them."""
    cost = {}
    for games in (150, 300):
        plain = _open_collection(t, games, probe=False)
        probed = _open_collection(t, games, probe=True)
        cost[games] = (plain, probed)
    (t.dir / "cost.txt").write_text("".join(
        f"{g} jogos x {TRACKS} faixas: off {p[0]} setores/{p[1]} reinícios, "
        f"on {q[0]} setores/{q[1]} reinícios\n" for g, (p, q) in cost.items()))
    extra = {g: q[0] - p[0] for g, (p, q) in cost.items()}
    # linear doubles; the quadratic rescan of the folder being listed makes it ~3.5x
    assert extra[300] <= 2.5 * extra[150], cost


# ---------------------------------------------------------------- real MSU-1 games
# CICLONE_MSU_COLLECTION=<image> made by tools/make_msu_collection.sh from your own game
# folders (real ROMs, .msu and .pcm tracks, copied over and over): game data never goes
# into the repo, so without it the test is skipped.
import os
import re
import subprocess
from pathlib import Path


def _set_config(img: Path, text: str):
    """config.yml and the menu under test onto a copy of the collection image."""
    out = subprocess.run(["hdiutil", "attach", "-nobrowse", str(img)], check=True,
                         capture_output=True, text=True).stdout
    dev = out.split()[0]
    mnt = Path([l.split("\t")[-1].strip() for l in out.splitlines() if "/Volumes/" in l][0])
    (mnt / "sd2snes" / "config.yml").write_bytes(text.replace("\n", "\r\n").encode())
    # the menu under test, not the one the image was made with
    for f in ("m3nu.bin", "igmenu.bin"):
        if (c.MENU_DIR / f).exists():
            (mnt / "sd2snes" / f).write_bytes((c.MENU_DIR / f).read_bytes())
    for p in mnt.rglob("._*"):
        p.unlink()
    subprocess.run(["sync"])
    for _ in range(5):
        if subprocess.run(["hdiutil", "detach", dev], capture_output=True).returncode == 0:
            return
    raise c.MenuError(f"detach failed: {img}")


class Fat32:
    """Just enough FAT32 to find which sectors a directory occupies."""

    def __init__(self, img: Path):
        import struct
        self.f = open(img, "rb")
        bs = self.f.read(512)
        _, self.spc, rsv, nfat = struct.unpack_from("<HBHB", bs, 11)
        fatsz, self.root = struct.unpack_from("<I", bs, 36)[0], struct.unpack_from("<I", bs, 44)[0]
        self.fat0, self.data0 = rsv, rsv + nfat * fatsz

    def chain(self, cl: int) -> list[int]:
        out = []
        while 2 <= cl < 0x0FFFFFF8:
            out.append(cl)
            self.f.seek(self.fat0 * 512 + cl * 4)
            cl = int.from_bytes(self.f.read(4), "little") & 0x0FFFFFFF
        return out

    def sectors(self, cl: int) -> set[int]:
        return {self.data0 + (c - 2) * self.spc + i for c in self.chain(cl) for i in range(self.spc)}

    def subdir(self, cl: int, name: str) -> int:
        data = b""
        for c_ in self.chain(cl):
            self.f.seek((self.data0 + (c_ - 2) * self.spc) * 512)
            data += self.f.read(self.spc * 512)
        lfn = []
        for o in range(0, len(data), 32):
            e = data[o:o + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5:
                lfn = []
                continue
            if e[11] == 0x0F:
                lfn.insert(0, (e[1:11] + e[14:26] + e[28:32]).decode("utf-16le", "ignore").split("\0")[0])
                continue
            n = "".join(lfn)
            lfn = []
            if n == name and e[11] & 0x10:
                return int.from_bytes(e[20:22], "little") << 16 | int.from_bytes(e[26:28], "little")
        raise c.MenuError(f"{name} not in the image")


def _open_real_collection(t, img: Path, probe: bool) -> dict:
    sd = t.dir / f"real_{'on' if probe else 'off'}.img"
    subprocess.run(["cp", "-c", str(img), str(sd)], check=True)
    _set_config(sd, "---\nOnboardingVersion: 255\nBootIntro: false\nResetPatch: false\n"
                    f"OpenMsuFolders: {'true' if probe else 'false'}\n")
    fat = Fat32(sd)
    coll = fat.sectors(fat.subdir(fat.root, COLLECTION))
    trace = t.dir / f"sdtrace_{'on' if probe else 'off'}.txt"
    m = t.menu(sd, env={"CICLONE_SD_TRACE": str(trace)})
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    m.goto(f"{COLLECTION}/")
    log0 = len(m.fwlog())
    tr0 = len(trace.read_text().splitlines())
    before = m.sdstat()
    m.press("A")
    pat = re.compile(r"path=/" + re.escape(COLLECTION) + r"\b.*?\n(?:.*\n)*?(\d+) entries")
    m.wait(lambda: pat.search(m.fwlog()[log0:]), frames=60000, every=10, what="o READDIR da coleção")
    m.settle()                  # the page's MSU-1 icons are settled after the listing
    after = m.sdstat()
    if probe:                   # every game folder of the collection holds one ROM + its .msu
        first = m.list_names()[1]
        assert m.tile_at(2, m.row_of(first))[0] == ICON_SNES, (first, m.text())
    reads = trace.read_text().splitlines()[tr0:]
    entries = int(pat.search(m.fwlog()[log0:]).group(1))
    m.close()
    sd.unlink()
    own = 0
    for r in reads:
        lba, n = map(int, r.split())
        own += sum(1 for s in range(lba, lba + n) if s in coll)
    res = {"entries": entries, "sectors": after[0] - before[0], "restarts": after[1] - before[1],
           "own": own, "own_size": len(coll)}
    t.log(f"real, OpenMsuFolders {probe}: {res}")
    return res


def test_real_msu_collection_listing_cost(t):
    """The same listing on real MSU-1 games: what the probe may add is reading each game
    folder once; the folder being listed itself is read about once, whatever the count."""
    img = os.environ.get("CICLONE_MSU_COLLECTION")
    if not img or not Path(img).is_file():
        raise c.Skip("CICLONE_MSU_COLLECTION: build one with tools/make_msu_collection.sh")
    off = _open_real_collection(t, Path(img), probe=False)
    on = _open_real_collection(t, Path(img), probe=True)
    (t.dir / "cost.txt").write_text(f"off: {off}\non:  {on}\n")
    assert on["entries"] == off["entries"], (off, on)
    assert on["own"] <= 2 * on["own_size"] + 2 * on["entries"], (off, on)


def test_msu_icons_follow_the_page(t):
    """Only the folders on the page being drawn are probed, and every page gets its icons:
    the first row of the next page shows the game icon once the browser scrolls to it."""
    m = t.menu(t.sd(extra=_collection(40), size_mb=2200, cluster=64))
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    m.goto(f"{COLLECTION}/")
    m.press("A")
    m.wait(lambda: m.has("Quest Saga 001 (MSU-1)/"), what="a coleção")
    m.settle()
    rows = m.u16("listdisp")
    last = f"Quest Saga {rows - 1:03d} (MSU-1)/"     # the last row of page 1 ("../" is row 0)
    nxt = f"Quest Saga {rows:03d} (MSU-1)/"
    assert m.has(last) and not m.has(nxt), m.text()
    for name in ("Quest Saga 001 (MSU-1)/", last):
        assert m.tile_at(2, m.row_of(name))[0] == ICON_SNES, (name, m.text())
    for _ in range(rows):
        m.press("DOWN")
    m.wait(lambda: m.has(nxt), what="a próxima página")
    m.settle()
    assert m.tile_at(2, m.row_of(nxt))[0] == ICON_SNES, m.text()


def test_held_dpad_scrolls_without_probing(t):
    """A held d-pad scrolls through folders nobody probed yet without asking the firmware
    for each row that comes in (each one is a walk of the folder); the page is asked for
    once the d-pad is released, and its rows get their icons then."""
    m = t.menu(t.sd(extra=_collection(80), size_mb=2200, cluster=64))
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    m.goto(f"{COLLECTION}/")
    m.press("A")
    m.wait(lambda: m.has("Quest Saga 001 (MSU-1)/"), what="a coleção")
    m.settle()
    probes = lambda: m.fwlog().count("cmd: 17\n")      # SNES_CMD_MSU_PROBE_PAGE
    before = probes()
    m.hold("DOWN")
    m.step(150)                                        # ~40 rows of auto-repeat
    during = probes() - before
    m.release()
    m.settle()
    name = m.selected()
    assert name.startswith("Quest Saga ") and name > "Quest Saga 030", (name, m.text())
    assert during == 0, f"{during} probes while the d-pad was held"
    assert probes() - before == 1, probes() - before
    assert m.tile_at(2, m.row_of(name))[0] == ICON_SNES, m.text()
