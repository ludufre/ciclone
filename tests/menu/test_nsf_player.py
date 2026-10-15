"""The browser's NSF player: A on a .nsf opens the player screen (the .pcm player's window with
the tune's title, artist and copyright), the firmware's 2A03 emulator renders it into a PSRAM
ring that the cartridge DAC plays; Left/Right change the song (wrapping), A pauses, L/R walk
the folder's .nsf files, B stops and puts the cursor back on the file.

The tune is synthetic: a 6502 program whose INIT holds pulse 1 on a fixed period chosen by
the song number and whose PLAY only counts frames."""
import ciclone as c

BLK = 0xFF4E00          # NSFPLAY_BLK: 'N','F', version, state, song, songs, pos, flags, strings
PLAYING, PAUSED, ERR_NSF = 1, 2, 4
TITLE_ROW = 15          # the players' window: spcstart_win_y (13) + 2
WIN_COLS = slice(8, 54)
CPU_HZ = 1789773
PERIODS = (0xFD, 0x7E, 0xA9)           # pulse timer per song: 440.4, 880.8, 658.0 Hz


def _nsf(title: str = "Probe Tune", artist: str = "Ciclone", copyright: str = "2026 Test") -> bytes:
    hdr = bytearray(0x80)
    hdr[0:5] = b"NESM\x1a"
    hdr[5] = 1
    hdr[6] = len(PERIODS)               # songs
    hdr[7] = 1                          # start
    hdr[8:10] = (0x8000).to_bytes(2, "little")     # load
    hdr[10:12] = (0x8000).to_bytes(2, "little")    # init
    hdr[12:14] = (0x8100).to_bytes(2, "little")    # play
    for off, s in ((0x0e, title), (0x2e, artist), (0x4e, copyright)):
        hdr[off:off + len(s)] = s.encode()
    hdr[0x6e:0x70] = (16666).to_bytes(2, "little")
    code = bytearray(0x200)
    init = bytes([
        0xAA,                           # TAX            (A = song - 1)
        0xBD, 0x20, 0x80,               # LDA $8020,X    the song's period
        0x8D, 0x02, 0x40,               # STA $4002
        0xA9, 0xBF, 0x8D, 0x00, 0x40,   # LDA #$BF / STA $4000: 50% duty, constant volume 15
        0xA9, 0x08, 0x8D, 0x01, 0x40,   # LDA #$08 / STA $4001: sweep off (negate: no mute)
        0xA9, 0x08, 0x8D, 0x03, 0x40,   # LDA #$08 / STA $4003: period high 0, length loaded
        0x60,                           # RTS
    ])
    code[0:len(init)] = init
    code[0x20:0x20 + len(PERIODS)] = bytes(PERIODS)
    code[0x100:0x103] = bytes([0xE6, 0x00, 0x60])  # PLAY: INC $00 / RTS
    return bytes(hdr) + bytes(code)


def _state(m) -> int:
    return m.psram(BLK + 3, 1)[0]


def _song(m) -> int:
    return m.psram(BLK + 4, 1)[0]


def _win(m, row: int) -> str:
    return m.screen()[row][WIN_COLS].strip()


def _ring_hz(m) -> float:
    """The tone the firmware rendered at the top of the PSRAM ring (s16 stereo, 44.1 kHz),
    from its zero crossings over 0.5 s, skipping the first 0.1 s (the DC blocker settling)."""
    raw = m.psram(0x000000 + 4410 * 4, 22050 * 4)
    left = [int.from_bytes(raw[i:i + 2], "little", signed=True) for i in range(0, len(raw), 4)]
    zc = sum((a >= 0) != (b >= 0) for a, b in zip(left, left[1:]))
    return zc / 2 / 0.5


def _open(m, name: str):
    m.goto("Two Games/")
    m.press("A")
    m.wait(lambda: m.has(name), what="the folder")
    m.settle()
    m.goto(name)
    m.press("A")


def test_nsf_plays_shows_the_header_and_stops(t):
    m = t.menu(t.sd(extra={"/Two Games/Tune.nsf": _nsf()}))
    _open(m, "Tune.nsf")
    m.wait(lambda: m.psram(BLK, 2) == b"NF" and _state(m) == PLAYING, what="the tune playing")
    assert m.psram(BLK + 5, 1)[0] == 3 and _song(m) == 1
    m.wait(lambda: m.dac_playing(), what="the DAC playing")
    m.wait(lambda: _win(m, TITLE_ROW) == "Probe Tune", what="the title row")
    assert _win(m, TITLE_ROW + 1) == "Ciclone"
    assert _win(m, TITLE_ROW + 2) == "2026 Test"
    assert _win(m, TITLE_ROW + 3).startswith(c.tr("text_nsf_song") + " 1/3"), _win(m, TITLE_ROW + 3)
    m.step(90)
    hz = _ring_hz(m)
    want = CPU_HZ / (16 * (PERIODS[0] + 1))
    assert abs(hz - want) < want * 0.01, (hz, want)
    m.wait(lambda: int.from_bytes(m.psram(BLK + 6, 2), "little") >= 1, what="the clock")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="the DAC released")
    m.settle()
    assert _state(m) == 0
    assert m.selected() == "Tune.nsf", m.text()
    assert m.u16("window_stack_head") == 0xFFFF
    m.close()


def test_nsf_left_right_change_the_song_and_wrap(t):
    m = t.menu(t.sd(extra={"/Two Games/Tune.nsf": _nsf()}))
    _open(m, "Tune.nsf")
    m.wait(lambda: m.psram(BLK, 2) == b"NF" and _state(m) == PLAYING, what="the tune playing")
    m.press("RIGHT")
    m.wait(lambda: _song(m) == 2, what="song 2")
    m.wait(lambda: _win(m, TITLE_ROW + 3).startswith(c.tr("text_nsf_song") + " 2/3"), what="row 3")
    m.step(90)
    want = CPU_HZ / (16 * (PERIODS[1] + 1))
    assert abs(_ring_hz(m) - want) < want * 0.01
    m.press("LEFT")
    m.wait(lambda: _song(m) == 1, what="song 1")
    m.press("LEFT")
    m.wait(lambda: _song(m) == 3, what="wrapped to the last song")
    m.press("RIGHT")
    m.wait(lambda: _song(m) == 1, what="wrapped to the first song")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="the DAC released")
    m.close()


def test_nsf_pause_and_resume(t):
    m = t.menu(t.sd(extra={"/Two Games/Tune.nsf": _nsf()}))
    _open(m, "Tune.nsf")
    m.wait(lambda: m.psram(BLK, 2) == b"NF" and _state(m) == PLAYING and m.dac_playing(),
           what="the tune playing")
    m.press("A")
    m.wait(lambda: _state(m) == PAUSED, what="the pause")
    m.wait(lambda: not m.dac_playing(), what="the DAC held")
    m.wait(lambda: c.tr("text_pcm_paused") in _win(m, TITLE_ROW + 3), what="'Paused'")
    m.press("A")
    m.wait(lambda: _state(m) == PLAYING and m.dac_playing(), what="the resume")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="the DAC released")
    m.close()


def test_nsf_l_r_walk_the_folder(t):
    m = t.menu(t.sd(extra={"/Two Games/A Tune.nsf": _nsf(title="First"),
                           "/Two Games/B Tune.nsf": _nsf(title="Second")}))
    _open(m, "A Tune.nsf")
    m.wait(lambda: _win(m, TITLE_ROW) == "First", what="the first file")
    m.press("R")
    m.wait(lambda: _win(m, TITLE_ROW) == "Second", what="the next file")
    assert _state(m) == PLAYING
    m.press("L")
    m.wait(lambda: _win(m, TITLE_ROW) == "First", what="back to the first")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="the DAC released")
    m.settle()
    assert m.selected() == "A Tune.nsf"
    m.close()


def test_nsf_that_is_not_one_shows_the_error(t):
    m = t.menu(t.sd(extra={"/Two Games/Bad.nsf": b"NOPE" + bytes(300)}))
    _open(m, "Bad.nsf")
    m.wait(lambda: m.psram(BLK, 2) == b"NF" and _state(m) == ERR_NSF, what="the format error")
    m.wait(lambda: _win(m, TITLE_ROW + 3) == c.tr("text_nsf_errnsf"), what="the message")
    assert not m.dac_playing()
    m.press("B")
    m.settle()
    assert m.selected() == "Bad.nsf"
    m.close()
