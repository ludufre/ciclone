"""A on a big folder while the cover lookup of that same folder is still running.

The cover of a folder walks up to 256 of its entries looking for an .msu. On a folder of
several hundred files and a card with real access time that takes longer than the browser's
wait for an idle MCU, and the READDIR the A sends was written while the MCU was still on the
cover: the firmware clears MCU_CMD when it gets back to its menu loop and the ready it sets
read as the READDIR's answer. The browser then showed the previous folder's table under the
new path, with a stale entry count (Up past the top listed garbage).

Command sync is off: with it the runner holds the SNES while the MCU works, which hides
exactly this race."""
import ciclone as c

ROMS, COVS = 543, 332
BIG = "Big Folder"


def _big() -> dict:
    files = {}
    for i in range(ROMS):
        stem = f"Generic Title Number {i:03d} - Subtitle (World) (Rev 1)"
        files[f"/{BIG}/{stem}.sfc"] = b""
        if i < COVS:
            files[f"/{BIG}/{stem}.cov"] = b""
    files[f"/{BIG}/patch one.ips"] = b""
    files[f"/{BIG}/patch two.bps"] = b""
    return files


def test_folder_opens_while_its_cover_lookup_runs(t):
    env = {"CICLONE_SYNC": "0", "CICLONE_SPEED": "1", "CICLONE_SD_DELAY_US": "6000"}
    m = t.menu(t.sd(extra=_big(), size_mb=2200, cluster=64), env=env)
    m.wait(lambda: m.has("Test Game.sfc"), what="a lista")
    m.settle()
    # the cursor boots on the folder and its cover is done by now: step off and back on
    m.press("DOWN")
    m.settle()
    m.press("UP", hold=2, after=0)
    m.wait(lambda: m.fwlog().count("cmd: 28") >= 2, frames=600, every=1, what="a capa da pasta")
    m.press("A", hold=2, after=1)
    try:            # with the race the listing never changes: give the MCU its time, then look
        m.wait(lambda: m.has("../"), frames=900, every=10, what="a pasta")
    except c.MenuError:
        pass
    m.settle()
    assert m.u16("dirend_addr") == (ROMS + 1) * 4, (hex(m.u16("dirend_addr")), m.text())
    assert m.list_names()[0] == "../", m.text()
    m.close()
