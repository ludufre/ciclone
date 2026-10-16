"""Clip soundtrack in QOA (<rom>.qoa next to the .fmv): the firmware decodes it into the PSRAM
ROM area, idle while the menu runs, and the FPGA SFX fetcher plays it from there. A .qoa wins
over a .pcm; a .qoa the DAC can't play (not 44.1 kHz, broken) falls back to the .pcm.

The clips are the reference-encoded fixtures of the firmware's own decoder test
(tests/host/qoa/), and the CRCs are of the reference decoder's output, so "decoded right" is
checked against the reference, not against another port."""
import time
import zlib

import ciclone as c
from test_pcm_player import GI, PCM, TILES, _fmv

FIX = c.SD2SNES / "tests" / "host" / "qoa"
STEREO = (FIX / "v1_stereo.qoa").read_bytes()      # 16597 frames, 2 ch
MONO = (FIX / "v2_mono.qoa").read_bytes()          # 11000 frames, 1 ch
STEREO_CRC, STEREO_LEN = 0xaf6737f1, 16597 * 4
MONO_CRC, MONO_LEN = 0xea9f03e0, 11000 * 4         # mono is played on both channels
INFO = "/sd2snes/info/TE/Test Game"
RUN = 0xC00000 - 0x21000 - 2048   # the PSRAM ROM area below the directory index, minus the pad
# What the first kick asks the fetcher for: the run and its pad, but under 8 MB -- on the base
# core with the mono body, bit 23 of the length is that flag (msu1.c MENUQOA_RUNCAP).
KICK = min(RUN + 2048, 0x7FF000)


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
    m.wait(lambda: m.sfx() == (0, KICK), what="the fetcher armed on the decoded clip")
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
    m.wait(lambda: m.sfx() == (0, KICK), what="the fetcher armed")
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
    assert m.sfx() != (0, KICK)
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


def _long_qoa(seconds: int) -> bytes:
    """A valid mono QOA of near-silence, `seconds` long: zero LMS state and every slice at
    scalefactor 0, index 0 -- what the decoder makes of it does not matter, only its length."""
    total = 44100 * seconds
    out = bytearray(b"qoaf" + total.to_bytes(4, "big"))
    left = total
    while left:
        n = min(5120, left)
        slices = (n + 19) // 20
        out += bytes([1]) + (44100).to_bytes(3, "big") + n.to_bytes(2, "big")
        out += (8 + 16 + slices * 8).to_bytes(2, "big") + bytes(16) + bytes(8 * slices)
        left -= n
    return bytes(out)


def _two_clips(t):
    """Two games with a 10 s clip each, the second's info bucket crowded like a real card, on a
    card slow enough for that to show; the first clip is shown three seconds in."""
    clip = _fmv(120)                                   # 10 s at 12 fps; its tiles are byte 0x40+i
    extra = {}
    for bb, stem, title in (("FI", "first", "Clip One"), ("SE", "second", "Clip Two")):
        base = f"/sd2snes/info/{bb}/{stem}"
        extra[base + ".yml"] = f'---\ntitle: "{title}"\nfmv: true\n'.encode()
        extra[base + ".fmv"] = clip
        extra[base + ".qoa"] = _long_qoa(10)
    for i in range(1500):                              # a crowded info bucket, like a real card
        extra[f"/sd2snes/info/SE/second filler {i:04d}.yml"] = b""
    m = t.menu(t.sd(extra=extra), env={"CICLONE_SD_DELAY_US": "300"})
    frame = lambda: m.psram(TILES, 1)[0] - 0x40
    m.goto("Two Games/")
    m.press("A")
    m.wait(lambda: m.has("first.sfc"), what="the folder")
    m.settle()
    m.goto("first.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Clip One"), what="the first clip")
    m.wait(lambda: frame() >= 36, frames=6000, what="three seconds into the first clip")
    return m, frame


def test_next_qoa_clip_starts_its_video_with_its_music(t):
    """Up/Down on the info screen moves to the next game's clip. After the soundtrack starts the
    load still makes a pass over the game's info folder for its guides, without decoding, and
    on a card with thousands of files the DAC plays through the decoded lead-in and the decoder
    holds it. The video clock is not updated while held, and the QOA path used to leave it at
    the PREVIOUS clip's position: the new video jumped there and froze until the music caught
    up (~7 s on a Mk.III). The new video has to start with its music."""
    m, frame = _two_clips(t)
    m.press("DOWN")
    m.wait(lambda: m.has("Clip Two"), frames=1200, what="the next game's screen")
    m.wait(lambda: m.fwlog().count("qoa: kick") == 2, frames=1200, what="its clip started")
    seen = set()
    t0 = time.time()
    while time.time() - t0 < 1.5:                       # the DAC model runs on the wall clock
        seen.add(frame())
        m.step(4)
    late = frame()
    assert late < 30 and len(seen) >= 4, f"the new video froze: {sorted(seen)}, now {late}"
    m.close()


def test_next_qoa_clip_is_opened_once(t):
    """Up/Down to a game with a clip: its GAME_INFO command opens the clip, and on a crowded card
    the rest of that command (the soundtrack's lead-in, the guides pass over the info folder)
    takes over 300 ms. The idle watchdog counted from the clip's opening, so it stopped the clip
    the moment the command ended and the first frame request opened the video and the music
    all over again: two more passes over the folder on every press."""
    m, frame = _two_clips(t)
    m.press("DOWN")
    m.wait(lambda: m.has("Clip Two"), frames=1200, what="the next game's screen")
    m.wait(lambda: m.fwlog().count("qoa: kick") >= 2, frames=1200, what="its clip started")
    t0 = time.time()
    while time.time() - t0 < 1.5:
        m.step(4)
    assert frame() > 0, "the new video did not play"
    assert m.fwlog().count("qoa: kick") == 2, "a clip was opened twice"
    m.close()
