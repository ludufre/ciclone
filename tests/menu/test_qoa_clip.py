"""Clip soundtrack in QOA (<rom>.qoa next to the .fmv): the firmware decodes it into the PSRAM
ROM area, idle while the menu runs, and the FPGA SFX fetcher plays it from there. A .qoa wins
over a .pcm; a .qoa the DAC can't play (not 44.1 kHz, broken) falls back to the .pcm.

The clips are the reference-encoded fixtures of the firmware's own decoder test
(tests/host/qoa/), and the CRCs are of the reference decoder's output, so "decoded right" is
checked against the reference, not against another port."""
import zlib

import ciclone as c
from test_pcm_player import GI, PCM, _fmv

FIX = c.SD2SNES / "tests" / "host" / "qoa"
STEREO = (FIX / "v1_stereo.qoa").read_bytes()      # 16597 frames, 2 ch
MONO = (FIX / "v2_mono.qoa").read_bytes()          # 11000 frames, 1 ch
STEREO_CRC, STEREO_LEN = 0xaf6737f1, 16597 * 4
MONO_CRC, MONO_LEN = 0xea9f03e0, 11000 * 4         # mono is played on both channels
INFO = "/sd2snes/info/TE/Test Game"
RUN = 0xC00000 - 2048          # the PSRAM ROM area minus the pad the run ends with


def _card(t, **files):
    extra = {INFO + ".yml": b'---\ntitle: "Clip Probe"\nfmv: true\n', INFO + ".fmv": _fmv(4)}
    extra.update({INFO + ext: data for ext, data in files.items()})
    return t.sd(extra=extra)


def _open_info(m):
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Clip Probe"), what="the info screen")
    assert m.psram(GI + 3, 1)[0] & 0x02, "clip not staged"


def _decoded(m, n):
    return zlib.crc32(m.psram(0x000000, n))


def test_qoa_clip_is_decoded_into_psram_and_played_by_the_fetcher(t):
    m = t.menu(_card(t, **{".qoa": STEREO, ".pcm": PCM}))
    _open_info(m)
    m.wait(lambda: m.sfx() == (0, RUN + 2048), what="the fetcher armed on the decoded clip")
    m.wait(lambda: m.dac_playing(), what="the DAC playing")
    m.wait(lambda: _decoded(m, STEREO_LEN) == STEREO_CRC, frames=600, what="the whole clip decoded")
    # the clip is laid out back to back until the area is full, then its start once more,
    # so the fetcher runs through the copies with no re-kick at every loop
    copies = RUN // STEREO_LEN
    end = copies * STEREO_LEN
    m.wait(lambda: zlib.crc32(m.psram(end - STEREO_LEN, STEREO_LEN)) == STEREO_CRC,
           frames=3000, what="the last copy decoded")
    assert zlib.crc32(m.psram(STEREO_LEN, STEREO_LEN)) == STEREO_CRC, "second copy"
    m.wait(lambda: m.psram(end, 2048) == m.psram(0x000000, 2048), frames=600,
           what="the pad after the run holding the clip start")
    assert m.fwlog().count("qoa: kick") == 1, "re-kicked before the end of the run"
    m.press("B")                                    # leaving the screen stops the clip
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="back to the browser")
    m.wait(lambda: not m.dac_playing(), what="the clip stopped")
    kicks = m.fwlog().count("qoa: kick")
    m.step(120)
    assert m.fwlog().count("qoa: kick") == kicks, "the clip kept looping after the screen closed"
    m.close()


def test_mono_qoa_plays_on_both_channels(t):
    m = t.menu(_card(t, **{".qoa": MONO}))
    _open_info(m)
    m.wait(lambda: m.sfx() == (0, RUN + 2048), what="the fetcher armed")
    m.wait(lambda: _decoded(m, MONO_LEN) == MONO_CRC, frames=600, what="the clip decoded")
    m.close()


def test_qoa_the_dac_cannot_play_falls_back_to_the_pcm(t):
    bad = bytearray(STEREO)
    bad[9:12] = (48000).to_bytes(3, "big")          # first frame header: 48 kHz
    m = t.menu(_card(t, **{".qoa": bytes(bad), ".pcm": PCM}))
    _open_info(m)
    m.wait(lambda: m.dac_playing(), what="the .pcm playing")
    m.step(60)
    assert "qoa: kick" not in m.fwlog()
    assert m.sfx() != (0, RUN + 2048)
    m.close()


def test_deleting_the_rom_takes_its_qoa_clip_audio(t):
    sd = _card(t, **{".qoa": STEREO, ".pcm": PCM})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    for _ in range(3):                             # Add to favorites, Cheats, Set as autoboot, Delete
        m.press("DOWN")
        m.settle(stable=6)
    m.press("A")
    m.wait_text(c.tr("text_confirm_delete_file"), frames=300)
    m.press("LEFT")                                # default = No; Yes is on the left
    m.settle(stable=6)
    m.press("A")
    m.wait(lambda: "Test Game.sfc" not in m.list_names(), what="the ROM gone from the list")
    m.close()
    left = t.listdir(sd, "/sd2snes/info/TE")
    assert not [n for n in left if n.startswith("Test Game.")], left
