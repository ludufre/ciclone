"""The browser's two music players: the .pcm one (an MSU-1 track on the cartridge DAC) and the
.spc one (a snapshot uploaded into the S-SMP).

.pcm: Left/Right seek by 5 s (held: bigger steps), a click on the bar seeks there, paused or
not; at the end of a track the folder's next .pcm plays (browser order: natural), and after the
last one the screen stays on "End"; L/R step through the folder; closing leaves the browser's
cursor on the track that was playing.

.spc: the same window, a clock, the ID666 length (play + fade) as "/ m:ss" with a bar; at the
end of it the next .spc of the folder, after the last one silence and "End"; A / R next, L
previous, B close.

Both with a mouse in port 1 (pad in port 2): left click = A, right click = B, the legends show
the mouse buttons, and on the .pcm bar a left click seeks."""
import re

import ciclone as c

BLK = 0xFF07C0          # PCMPLAY_BLK: 'P','C', version, state, pos, total, progress
PLAYING, PAUSED, ENDED = 1, 2, 5
MOUSE = {"CICLONE_PORT1": "mouse"}
BPS = 44100 * 4


def _pcm(seconds: float, level: int = 6000) -> bytes:
    """An MSU-1 .pcm: "MSU1", loop point 0, then a square wave (stereo 16-bit, 44.1 kHz)."""
    hi = level.to_bytes(2, "little", signed=True) * 2
    lo = (-level).to_bytes(2, "little", signed=True) * 2
    period = hi * 50 + lo * 50
    n = int(44100 * seconds)
    body = (period * (n // 100 + 1))[: n * 4]
    return b"MSU1" + bytes(4) + body


TITLE_ROW = 15          # the players' window: spcstart_win_y (13) + 2, the first text row


WIN_COLS = slice(8, 54)   # inside the window (spcstart_win_x 10, w 44): the list shows around it


def _win(m, row: int) -> str:
    return m.screen()[row][WIN_COLS].strip()


def _title(m) -> str:
    """The window's first row: the track (the browser's list stays visible above it, so a
    plain m.has(name) would also find the name there)."""
    return _win(m, TITLE_ROW)


def _keys(m) -> str:
    """The window's two key-legend rows (layout rows 5 and 6): the browser's own status bar
    stays on screen below, with its keys drawn whenever it last was."""
    return _win(m, TITLE_ROW + 5) + " " + _win(m, TITLE_ROW + 6)


def _state(m) -> int:
    return m.psram(BLK + 3, 1)[0]


def _pos(m) -> int:
    return int.from_bytes(m.psram(BLK + 4, 2), "little")


def _open_pcm(m, folder: str, name: str, pad: int = 1):
    m.goto(folder, pad=pad)
    m.press("A", pad=pad)
    m.wait(lambda: m.has(name), what="a pasta")
    m.settle()
    m.goto(name, pad=pad)
    m.press("A", pad=pad)
    m.wait(lambda: m.psram(BLK, 2) == b"PC" and _state(m) == PLAYING, what="a faixa tocando")
    m.wait(lambda: m.dac_playing(), what="o DAC tocando")


# ---------------------------------------------------------------- .pcm: seek

def test_pcm_left_right_seek(t):
    m = t.menu(t.sd(extra={"/Music/Long.pcm": _pcm(40)}))
    _open_pcm(m, "Music/", "Long.pcm")
    assert m.psram(BLK + 2, 1)[0] >= 2, "firmware sem seek"
    m.press("RIGHT")
    m.wait(lambda: 5 <= _pos(m) <= 7, what="+5 s")
    m.press("RIGHT")
    m.wait(lambda: 10 <= _pos(m) <= 12, what="+10 s")
    m.press("LEFT")
    m.wait(lambda: 5 <= _pos(m) <= 7, what="-5 s")
    assert _state(m) == PLAYING and m.dac_playing()
    m.settle(stable=4)
    assert m.has("0:0"), m.text()                 # the clock moved with it (0:05..0:07)
    for _ in range(3):
        m.press("LEFT")
    m.wait(lambda: _pos(m) <= 2, what="o começo (sem passar de 0)")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.close()


def test_pcm_seek_while_paused_keeps_the_pause(t):
    m = t.menu(t.sd(extra={"/Music/Long.pcm": _pcm(40)}))
    _open_pcm(m, "Music/", "Long.pcm")
    m.press("A")
    m.wait(lambda: _state(m) == PAUSED and not m.dac_playing(), what="a pausa")
    p0 = _pos(m)
    m.press("RIGHT")
    m.press("RIGHT")
    m.wait(lambda: _pos(m) >= p0 + 10, what="+10 s pausado")
    m.step(30)
    assert _state(m) == PAUSED and not m.dac_playing(), "o seek despausou"
    p1 = _pos(m)
    m.step(60)
    assert _pos(m) == p1, "a posição andou pausada"
    m.press("A")
    m.wait(lambda: _state(m) == PLAYING and m.dac_playing(), what="a retomada")
    assert _pos(m) >= p1
    m.close()


def test_pcm_held_seek_speeds_up(t):
    """Held, Left/Right repeat and the step grows: well past what 5 s steps would cover."""
    m = t.menu(t.sd(extra={"/Music/Long.pcm": _pcm(120)}))
    _open_pcm(m, "Music/", "Long.pcm")
    m.hold("RIGHT")
    m.step(70)                                    # 16 frames to the first repeat, then every 3
    m.release()
    m.step(6)
    # 70 frames = the press + 18 repeats, every other one a seek: 1 + 9 seeks.  At 5 s each
    # that would be 50 s; growing steps go further.
    assert _pos(m) > 60, _pos(m)
    m.close()


# ---------------------------------------------------------------- .pcm: the folder

def test_pcm_end_plays_the_next_track_then_stops(t):
    """Natural order (T2 before T10), one after the other, "End" after the last; B leaves the
    browser on the last one played."""
    sd = t.sd(extra={"/Music/T10.pcm": _pcm(1.0), "/Music/T2.pcm": _pcm(1.0)})
    m = t.menu(sd)
    _open_pcm(m, "Music/", "T2.pcm")
    m.wait(lambda: _title(m) == "T10.pcm" and _state(m) == PLAYING, frames=2400, what="a próxima faixa")
    m.wait(lambda: _state(m) == ENDED, frames=2400, what="o fim da última")
    m.settle(stable=6)
    assert m.has(c.tr("text_pcm_ended")), m.text()
    assert not m.dac_playing()
    m.press("A")                                  # "End": A starts over from the first
    m.wait(lambda: _title(m) == "T2.pcm" and _state(m) == PLAYING and m.dac_playing(),
           what="de volta à primeira")
    m.press("R")
    m.wait(lambda: _title(m) == "T10.pcm" and _state(m) == PLAYING, what="R: a próxima")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.settle()
    assert m.selected() == "T10.pcm", m.selected()
    assert m.u16("window_stack_head") == 0xFFFF
    m.close()


def test_pcm_l_r_walk_the_folder(t):
    sd = t.sd(extra={"/Music/A.pcm": _pcm(20), "/Music/B.pcm": _pcm(20),
                     "/Music/C.pcm": _pcm(20), "/Music/game.sfc": b"\x00" * 0x8000})
    m = t.menu(sd)
    _open_pcm(m, "Music/", "B.pcm")
    m.press("L")
    m.wait(lambda: _title(m) == "A.pcm" and _state(m) == PLAYING, what="L: a anterior")
    m.press("L")                                  # the first: nothing before it
    m.step(20)
    assert _title(m) == "A.pcm" and _state(m) == PLAYING, m.text()
    m.press("R")
    m.wait(lambda: _title(m) == "B.pcm" and _state(m) == PLAYING, what="R: a do meio")
    m.press("R")
    m.wait(lambda: _title(m) == "C.pcm" and _state(m) == PLAYING, what="R: a última")
    m.press("R")                                  # the last: nothing after it
    m.step(20)
    assert _title(m) == "C.pcm", m.text()
    m.press("B")
    m.settle()
    assert m.selected() == "C.pcm", m.selected()
    m.close()


# ---------------------------------------------------------------- .pcm: mouse

BAR_ROW, BAR_COL = TITLE_ROW + 2, 16      # layout row 2; spcstart_win_x (10) + 2 + PCM_BAR_X (4)


def _bar(m):
    """Screen pixel x of bar cell 0 (half-column h = pixels 4h..4h+3) and a pixel y on the
    bar's text row (the list scrolls by 13 lines: row r = lines 8r-13..8r-6)."""
    return BAR_COL * 4 + 2, BAR_ROW * 8 - 9


def _point(m, x: int, y: int):
    from test_mouse import _point as p
    p(m, x, y)


def test_pcm_mouse_click_on_the_bar_seeks(t):
    m = t.menu(t.sd(extra={"/Music/Long.pcm": _pcm(40)}), env=MOUSE)
    _open_pcm(m, "Music/", "Long.pcm", pad=2)
    m.settle(stable=4)
    x0, y = _bar(m)
    _point(m, x0 + 16 * 4, y)                     # cell 16 of 32: the middle
    m.mouse_click("left")
    m.wait(lambda: 19 <= _pos(m) <= 23, what="o meio da faixa")
    assert _state(m) == PLAYING, "o clique na barra pausou"
    _point(m, x0 + 2 * 4, y)                      # paused, a click still seeks
    _point(m, x0 + 20 * 4, y + 16)                # off the bar: A = pause
    m.mouse_click("left")
    m.wait(lambda: _state(m) == PAUSED, what="a pausa pelo clique")
    _point(m, x0 + 2 * 4, y)
    m.mouse_click("left")
    m.wait(lambda: _pos(m) <= 4, what="o seek pausado")
    assert _state(m) == PAUSED
    m.mouse_click("right")                        # B: close
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.settle()
    assert m.selected() == "Long.pcm"
    assert m.u16("window_stack_head") == 0xFFFF
    m.close()


def test_pcm_mouse_pointer_and_legend(t):
    m = t.menu(t.sd(extra={"/Music/Long.pcm": _pcm(40)}), env=MOUSE)
    _open_pcm(m, "Music/", "Long.pcm", pad=2)
    m.settle(stable=4)
    assert m.peek("oam", 64 * 4 + 1, 1)[0] < 0xE0, "o ponteiro sumiu"
    keys = _keys(m)
    assert "A:" not in keys and "B:" not in keys, keys
    assert "Ⓛ" in keys and "Ⓡ" in keys, keys   # left / right buttons
    m.press("RIGHT", pad=2)                       # the pad in port 2 still seeks
    m.wait(lambda: _pos(m) >= 5, what="+5 s pelo controle 2")
    m.close()


# ---------------------------------------------------------------- .spc

SPC = (c.SD2SNES / "misc" / "menu.spc").read_bytes()


def _spc(song: str, game: str = "", artist: str = "", secs: int = 0, fade_ms: int = 0) -> bytes:
    """menu.spc with an ID666 tag in the text format: length (3 digits), fade (5 digits)."""
    b = bytearray(SPC)
    b[0x23] = 0x1A
    for off, n in ((0x2E, 32), (0x4E, 32), (0x6E, 16), (0x7E, 32), (0x9E, 11), (0xA9, 3), (0xAC, 5),
                   (0xB1, 32)):
        b[off:off + n] = bytes(n)
    b[0x2E:0x2E + len(song)] = song.encode()
    b[0x4E:0x4E + len(game)] = game.encode()
    b[0xB1:0xB1 + len(artist)] = artist.encode()
    b[0xA9:0xAC] = f"{secs:03d}".encode()
    b[0xAC:0xB1] = f"{fade_ms:05d}".encode()
    return bytes(b)


def _clock(m) -> str:
    return _win(m, TITLE_ROW + 3)


def _spc_playing(m) -> bool:
    """Uploaded and running: the clock row shows m:ss ("Loading..." while uploading)."""
    return re.match(r"\d+:\d\d", _clock(m)) is not None and c.tr("text_pcm_ended") not in _clock(m)


def _open_spc(m, folder: str, name: str, pad: int = 1):
    m.goto(folder, pad=pad)
    m.press("A", pad=pad)
    m.wait(lambda: m.has(name), what="a pasta")
    m.settle()
    m.goto(name, pad=pad)
    m.press("A", pad=pad)
    m.wait(lambda: m.has(c.tr("text_spcplay")) and _spc_playing(m), frames=1800, what="o SPC tocando")


def test_spc_window_tag_and_clock(t):
    sd = t.sd(config="---\nEnableMenuMusic: false\n",
              extra={"/Music/One.spc": _spc("Probe Song", "Probe Game", "Probe Band", 90, 10000)})
    m = t.menu(sd)
    _open_spc(m, "Music/", "One.spc")
    assert _title(m) == "Probe Song", m.text()
    assert m.has("Probe Game - Probe Band"), m.text()
    m.wait(lambda: _clock(m) == "0:02 / 1:40", frames=600, what="o relógio (90 s + 10 s de fade)")
    assert m.has(c.tr("text_spc_prompt").split()[0]), m.text()
    m.press("B")
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.settle()
    assert m.selected() == "One.spc", m.selected()
    assert not m.has(c.tr("text_spcplay")), m.text()
    m.close()


def test_spc_length_runs_out_into_the_next_then_end(t):
    sd = t.sd(config="---\nEnableMenuMusic: false\n",
              extra={"/Music/A.spc": _spc("First Tune", secs=2), "/Music/B.spc": _spc("Second Tune", secs=2)})
    m = t.menu(sd)
    _open_spc(m, "Music/", "A.spc")
    m.wait(lambda: _title(m) == "Second Tune" and _spc_playing(m), frames=1200, what="a próxima")
    m.wait(lambda: c.tr("text_pcm_ended") in _clock(m), frames=1200, what="o fim da última")
    m.settle(stable=6)
    assert m.has(c.tr("text_pcm_ended")), m.text()
    m.press("A")                                  # "End": the folder again from the top
    m.wait(lambda: _title(m) == "First Tune" and _spc_playing(m), frames=1200, what="de volta à primeira")
    m.press("B")
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.settle()
    assert m.selected() == "A.spc", m.selected()
    m.close()


def test_spc_l_r_and_mouse(t):
    sd = t.sd(config="---\nEnableMenuMusic: false\n",
              extra={"/Music/A.spc": _spc("First Tune"), "/Music/B.spc": _spc("Second Tune")})
    m = t.menu(sd, env=MOUSE)
    _open_spc(m, "Music/", "A.spc", pad=2)
    assert "/" not in _clock(m), _clock(m)       # no length: a clock without "/ m:ss"
    m.press("R", pad=2)
    m.wait(lambda: _title(m) == "Second Tune" and _spc_playing(m), frames=1200, what="R: a próxima")
    m.press("L", pad=2)
    m.wait(lambda: _title(m) == "First Tune" and _spc_playing(m), frames=1200, what="L: a anterior")
    m.wait(lambda: "Ⓛ" in _keys(m) and "A:" not in _keys(m),
           what="a legenda com o mouse")   # (a warm reset re-reads the mouse: a frame later)
    m.mouse_click("left")                         # left click = A = the next track
    m.wait(lambda: _title(m) == "Second Tune" and _spc_playing(m), frames=1200, what="clique: a próxima")
    m.mouse_click("right")                        # right click = B
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.settle()
    assert m.selected() == "B.spc", m.selected()
    m.close()


def _bgm(m) -> int:
    return m.peek("snescmd", 0x2F7, 1)[0]         # BGM_STATE ($2AF7): 1 = the menu music plays


def test_spc_hands_the_menu_music_back(t):
    """With the menu music on: the player stops it (a warm reset), and closing brings it back
    -- a track change in between included."""
    sd = t.sd(misc=True, extra={"/Music/A.spc": _spc("First Tune"), "/Music/B.spc": _spc("Second Tune")})
    m = t.menu(sd)
    m.wait(lambda: _bgm(m) == 1, frames=1200, what="a música do menu")
    _open_spc(m, "Music/", "A.spc")
    m.press("R")
    m.wait(lambda: _title(m) == "Second Tune" and _spc_playing(m), frames=1200, what="R: a próxima")
    m.press("B")
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.wait(lambda: _bgm(m) == 1, frames=1200, what="a música do menu de volta")
    m.settle()
    assert m.selected() == "B.spc", m.selected()
    m.close()


def _list_pal(m) -> int:
    """Print palette of the first list row's name (text row 9): greyed while a modal is up."""
    return m.tile_at(8, 9)[1]


def test_players_grey_the_browser_like_a_modal(t):
    sd = t.sd(config="---\nEnableMenuMusic: false\n",
              extra={"/Music/Long.pcm": _pcm(40), "/Music/A.spc": _spc("First Tune"),
                     "/Music/B.spc": _spc("Second Tune")})
    m = t.menu(sd)
    m.goto("Music/")
    m.press("A")
    m.wait(lambda: m.has("Long.pcm"), what="a pasta")
    m.settle()
    bright = _list_pal(m)
    m.goto("Long.pcm")
    m.press("A")
    m.wait(lambda: _state(m) == PLAYING, what="a faixa tocando")
    m.settle(stable=4)
    assert _list_pal(m) != bright, "o browser não ficou cinza atrás do tocador de .pcm"
    m.press("B")
    m.settle()
    assert _list_pal(m) == bright, "o browser não voltou ao normal"
    for _ in range(3):                            # goto only walks down: back up to the .spc
        if m.selected() == "A.spc":
            break
        m.press("UP")
        m.settle(stable=8)
    assert m.selected() == "A.spc", m.selected()
    m.press("A")
    m.wait(lambda: m.has(c.tr("text_spcplay")) and _spc_playing(m), frames=1800, what="o SPC tocando")
    assert _list_pal(m) != bright, "o browser não ficou cinza atrás do SPC player"
    m.press("R")                                  # a track change repaints the list (warm reset)
    m.wait(lambda: _title(m) == "Second Tune" and _spc_playing(m), frames=1200, what="R: a próxima")
    assert _list_pal(m) != bright, "o browser voltou a acender depois da troca de faixa"
    m.press("B")
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.settle()
    assert _list_pal(m) == bright, "o browser não voltou ao normal"
    m.close()


def _left(m) -> list[str]:
    """Columns 0-7 of every list row: the part of the list the player's window leaves visible."""
    return [r[:8] for r in m.screen()[9:28]]


def test_spc_track_change_keeps_the_list_in_place_and_fades(t):
    """A track change is a warm reset that repaints the list behind the player: the list has to
    come back on its rows (it came back shifted down, starting where the last repaint ended),
    and the screen goes black and fades back in instead of flashing (cur_bright back to the
    level it had). With the menu music on, opening and closing reset the console too."""
    ex = {f"/Music/{n}.spc": _spc(f"Tune {n}") for n in "ABC"}
    for i in range(12):
        ex[f"/Music/f{i:02d}.sfc"] = b"\0" * 0x8000
    m = t.menu(t.sd(misc=True, extra=ex))
    m.wait(lambda: _bgm(m) == 1, frames=1200, what="a música do menu")
    m.goto("Music/")
    m.press("A")
    m.wait(lambda: m.has("A.spc"), what="a pasta")
    m.settle()
    level = m.u8("menu_brightness")
    m.wait(lambda: m.u8("cur_bright") == level, what="o browser aceso")
    first = m.screen()[9]
    assert "../" in first, first
    left = _left(m)                               # the list as the browser draws it
    m.goto("B.spc")
    m.press("A")
    m.wait(lambda: _title(m) == "Tune B" and _spc_playing(m), frames=1800, what="o SPC tocando")
    m.wait(lambda: m.u8("cur_bright") == level, what="o fade de volta")
    for key, want in (("R", "Tune C"), ("L", "Tune B"), ("L", "Tune A")):
        m.press(key)
        low = [level]
        def changed():
            low[0] = min(low[0], m.u8("cur_bright"))
            return _title(m) == want and _spc_playing(m)
        m.wait(changed, frames=1800, what=f"{key}: {want}")
        assert low[0] == 0, f"{key}: sem fade (o brilho só desceu a {low[0]})"
        m.wait(lambda: m.u8("cur_bright") == level, what="o fade de volta")
        assert _left(m) == left, f"a lista saiu do lugar depois de {key}\n{m.text()}"
    m.press("B")
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.wait(lambda: m.u8("cur_bright") == level, frames=300, what="o browser aceso de novo")
    m.wait(lambda: _bgm(m) == 1, frames=1200, what="a música do menu de volta")
    m.settle()
    assert m.selected() == "A.spc", m.selected()
    assert _left(m) == left, m.text()
    m.close()


def test_spc_legend_waits_for_the_mouse_through_the_load(t):
    """The upload resets the console, which forgets the mouse until the pad is read again: the
    key legend stays hidden while loading and comes up with the mouse buttons at once, instead
    of showing A/B and flipping to the mouse buttons a frame later (across a track change too)."""
    sd = t.sd(config="---\nEnableMenuMusic: false\n",
              extra={"/Music/A.spc": _spc("First Tune"), "/Music/B.spc": _spc("Second Tune")})
    m = t.menu(sd, env=MOUSE)
    m.goto("Music/", pad=2)
    m.press("A", pad=2)
    m.wait(lambda: m.has("A.spc"), what="a pasta")
    m.settle()
    m.goto("A.spc", pad=2)
    for key, want in (("A", "First Tune"), ("R", "Second Tune")):
        m.press(key, pad=2)
        seen = []
        for _ in range(400):
            m.step(1)
            k = _keys(m)
            if k.strip():
                seen.append(k)
            if _title(m) == want and _spc_playing(m) and len(seen) > 20:
                break
        assert seen, f"{key}: a legenda não apareceu"
        bad = [k for k in seen if "A:" in k or "B:" in k]
        assert not bad, f"{key}: a legenda mostrou A/B antes dos botões do mouse: {bad[0]!r}"
        assert "Ⓛ" in seen[-1], seen[-1]
    m.close()


def test_mouse_held_buttons_step_tracks_and_legend_drops_the_seek_keys(t):
    """With a mouse in, the players' second key row shows the held buttons (right = previous
    track, left = next) instead of the d-pad seek keys a mouse cannot press; holding the left
    button steps to the next track without the release acting as a click (no pause, no seek),
    holding the right one steps back."""
    sd = t.sd(extra={"/Music/A.pcm": _pcm(20), "/Music/B.pcm": _pcm(20), "/Music/C.pcm": _pcm(20)})
    m = t.menu(sd, env=MOUSE)
    _open_pcm(m, "Music/", "B.pcm", pad=2)
    m.settle(stable=4)
    keys = _keys(m)
    assert "<>" not in keys and "-5s" not in keys, keys
    assert "ⓇⒽ" in keys and "ⓁⒽ" in keys, keys     # right held, left held
    m.mouse(left=True)
    m.step(40)                                     # past MOUSE_RHOLD
    m.mouse()
    m.wait(lambda: _title(m) == "C.pcm" and _state(m) == PLAYING, what="esquerdo segurado: a próxima")
    m.step(20)
    assert _state(m) == PLAYING, "a soltura do esquerdo virou clique (pausa)"
    m.mouse(right=True)
    m.step(40)
    m.mouse()
    m.wait(lambda: _title(m) == "B.pcm" and _state(m) == PLAYING, what="direito segurado: a anterior")
    m.step(20)
    assert m.has(c.tr("text_pcm_title")), "a soltura do direito fechou o tocador"
    m.close()


def test_pcm_legend_never_shows_a_half_drawn_row(t):
    """The key legend is printed first and its keys turned into glyphs right after: an NMI in
    between uploads the row with the raw letters ("Y: Prev track") for a frame -- a flicker.
    The clock's ticks must not redraw the legend at all, and a full redraw (pause, track
    change) must finish it inside one frame. Sampled frame by frame, with a mouse in."""
    sd = t.sd(extra={"/Music/A.pcm": _pcm(30), "/Music/B.pcm": _pcm(30)})
    m = t.menu(sd, env=MOUSE)
    _open_pcm(m, "Music/", "A.pcm", pad=2)
    m.wait(lambda: "Ⓛ" in _keys(m), what="a legenda com o mouse")
    bad, clocks = [], set()

    def watch(frames):
        for _ in range(frames):
            m.step(1)
            k = _keys(m)
            clocks.add(_clock(m))
            if any(s in k for s in ("A:", "B:", "Y:", "Z:")):
                bad.append(k)

    watch(600)                                     # the clock ticking
    for _ in range(3):
        m.mouse_click("left", hold=2, after=0)     # pause / resume: full redraws
        watch(40)
    m.press("R", pad=2)                            # a track change
    watch(60)
    assert len(clocks) > 2, clocks                 # the clock did tick meanwhile
    assert not bad, f"{len(bad)} quadros com a legenda crua, ex.: {bad[0]!r}"
    m.close()
