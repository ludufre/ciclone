"""Repeat in the browser's music players (.pcm, .spc, .nsf): X toggles it, a row under the key
legend says so ("X: Repeat  On/Off", the key in green, the both-buttons glyph with a mouse), it
starts off and is saved into config.yml (PlayerRepeat) when the player closes.

  .pcm  on: the module lets the engine loop the track at its header's loop point, so a track
        that would have ended (and handed over to the folder's next .pcm) keeps playing.
  .spc  on: when the ID666 length runs out, the same track is loaded again.
  .nsf  a song is over once it has been silent for 3 s (the module decides); off: the next
        song, after the file's last one the folder's next .nsf, after the last file "End";
        on: the same song again.  A song that never falls silent never ends.

The DAC model runs on the real clock, so the long waits here are in wall seconds."""
import time

import ciclone as c
from test_media_players import _pcm, _spc, _open_pcm, _open_spc, _title, _clock, _spc_playing
from test_nsf_player import _nsf

CFG_PLAYER_REPEAT = 0xFF0100 + 0x1D9      # CFG_ADDR + $1D9 (src/cfg.h player_repeat)
PCM_BLK = 0xFF07C0
NSF_BLK = 0xFF4E00
PLAYING, ENDED = 1, 5
TITLE_ROW = 15
REPEAT_ROW = TITLE_ROW + 7                # layout row 7, under the two key-legend rows
WIN_COLS = slice(8, 54)
MOUSE = {"CICLONE_PORT1": "mouse"}


def _row(m) -> str:
    return m.screen()[REPEAT_ROW][WIN_COLS].strip()


def _want(on: bool, lang: str = "en") -> str:
    return c.tr("text_media_repeat", lang) + "  " + c.tr("text_on" if on else "text_off", lang)


def _repeat(m) -> int:
    return m.psram(CFG_PLAYER_REPEAT, 1)[0]


def _for_secs(m, secs: float, pred=None, every: int = 2):
    """Steps for `secs` wall seconds (the DAC's clock); stops early when pred() turns true."""
    t0 = time.time()
    while time.time() - t0 < secs:
        m.step(every)
        if pred and pred():
            return True
    return False


def _pcm_state(m) -> int:
    return m.psram(PCM_BLK + 3, 1)[0]


def _pcm_pos(m) -> int:
    return int.from_bytes(m.psram(PCM_BLK + 4, 2), "little")


# ---------------------------------------------------------------- the toggle

def test_repeat_row_toggles_and_is_saved_on_close(t):
    """Off by default; X flips the live CFG byte and the row at once; config.yml gets it only
    when the player closes (nothing is written to the card while the track streams)."""
    sd = t.sd(extra={"/Music/Long.pcm": _pcm(30)})
    m = t.menu(sd)
    assert _repeat(m) == 0
    _open_pcm(m, "Music/", "Long.pcm")
    m.wait(lambda: _row(m) == _want(False), what="a linha Repetir (Des)")
    # the key in green (hint_keys): the X cell's palette differs from a letter of the word
    # after it.  Half-columns: the row starts at spcstart_win_x (10) + 2.
    assert m.tile_at(12, REPEAT_ROW)[1] != m.tile_at(16, REPEAT_ROW)[1], "a tecla X não saiu verde"
    saves0 = m.fwlog().count("cmd: 14\n")         # SNES_CMD_SAVE_CFG
    m.press("X")
    m.wait(lambda: _row(m) == _want(True), what="Repetir: Lig")
    assert _repeat(m) == 1
    assert m.dac_playing() and _pcm_state(m) == PLAYING, "o X mexeu na reprodução"
    m.step(60)
    assert m.fwlog().count("cmd: 14\n") == saves0, "o config.yml foi gravado durante a reprodução"
    m.press("X")
    m.wait(lambda: _row(m) == _want(False), what="Repetir: Des de novo")
    m.press("X")
    m.wait(lambda: _row(m) == _want(True), what="Repetir: Lig de novo")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.settle()
    assert m.selected() == "Long.pcm"
    assert m.u16("window_stack_head") == 0xFFFF
    assert m.fwlog().count("cmd: 14\n") == saves0 + 1, "o fechamento não gravou (ou gravou 2x)"
    m.close()
    cfg = t.read(sd, "/sd2snes/config.yml").decode()
    assert "PlayerRepeat: true" in cfg, cfg


def test_repeat_from_config_and_unchanged_is_not_saved(t):
    """PlayerRepeat: true comes up On; closing without a change does not rewrite config.yml."""
    sd = t.sd(config="---\nPlayerRepeat: true\n", extra={"/Music/Long.pcm": _pcm(30)})
    m = t.menu(sd)
    assert _repeat(m) == 1
    _open_pcm(m, "Music/", "Long.pcm")
    m.wait(lambda: _row(m) == _want(True), what="Repetir: Lig (do config.yml)")
    saves0 = m.fwlog().count("cmd: 14\n")
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.settle()
    assert m.fwlog().count("cmd: 14\n") == saves0, "fechou sem mudança e gravou o config.yml"
    m.close()
    assert "PlayerRepeat: true" in t.read(sd, "/sd2snes/config.yml").decode()


def test_repeat_row_is_translated(t):
    sd = t.sd(config="---\nLanguage: 1\n", extra={"/Music/Long.pcm": _pcm(30)})
    m = t.menu(sd)
    _open_pcm(m, "Music/", "Long.pcm")
    want = c.encode_menu_text(_want(False, "ptbr"))
    m.wait(lambda: _row(m) == want, what=f"a linha em pt-BR ({want!r})")
    m.close()


def test_repeat_with_a_mouse_both_buttons(t):
    """With a mouse: the row shows the both-buttons glyph instead of "X:", and a click with
    both buttons (X, mouse_b_word) toggles it."""
    m = t.menu(t.sd(extra={"/Music/Long.pcm": _pcm(30)}), env=MOUSE)
    _open_pcm(m, "Music/", "Long.pcm", pad=2)
    m.wait(lambda: "Ⓑ" in _row(m), what="o glifo dos dois botões")
    assert "X:" not in _row(m), _row(m)
    m.mouse(left=True, right=True)
    m.step(3)
    m.mouse()
    m.step(3)
    m.wait(lambda: _repeat(m) == 1, what="Repetir ligado pelo mouse")
    assert _pcm_state(m) == PLAYING, "o clique duplo pausou"
    m.close()


# ---------------------------------------------------------------- .pcm

def test_pcm_repeat_loops_the_track_instead_of_moving_on(t):
    """Two 1 s tracks: with Repeat on the first one keeps coming back (its clock wraps to the
    loop point) and the second never starts; turned off, the folder walk resumes."""
    # on from config.yml: a 1 s track could run out before an X press lands
    sd = t.sd(config="---\nPlayerRepeat: true\n",
              extra={"/Music/T10.pcm": _pcm(1.0), "/Music/T2.pcm": _pcm(1.0)})
    m = t.menu(sd)
    _open_pcm(m, "Music/", "T2.pcm")
    assert _repeat(m) == 1
    seen_end = []
    moved = _for_secs(m, 4.0, lambda: (seen_end.append(1) if _pcm_state(m) == ENDED else None)
                      or _title(m) != "T2.pcm")
    assert not moved, f"com Repetir a pasta andou: {_title(m)}"
    assert not seen_end, "com Repetir a faixa chegou ao fim (ENDED)"
    assert _pcm_state(m) == PLAYING and m.dac_playing()
    assert _pcm_pos(m) <= 1
    m.press("X")
    m.wait(lambda: _repeat(m) == 0, what="Repetir desligado")
    assert _for_secs(m, 6.0, lambda: _title(m) == "T10.pcm"), "sem Repetir a próxima não veio"
    m.close()


# ---------------------------------------------------------------- .spc

def test_spc_repeat_reloads_the_same_track(t):
    sd = t.sd(config="---\nEnableMenuMusic: false\nPlayerRepeat: true\n",
              extra={"/Music/A.spc": _spc("First Tune", secs=2), "/Music/B.spc": _spc("Second Tune", secs=2)})
    m = t.menu(sd)
    _open_spc(m, "Music/", "A.spc")
    m.wait(lambda: _row(m) == _want(True), what="Repetir: Lig")
    m.wait(lambda: _clock(m).startswith("0:02"), frames=600, what="o fim da duração")
    m.wait(lambda: _clock(m).startswith("0:00") and _spc_playing(m), frames=1200,
           what="a mesma faixa recarregada")
    assert _title(m) == "First Tune", m.text()
    m.wait(lambda: _clock(m).startswith("0:02"), frames=600, what="o fim de novo")
    m.wait(lambda: _clock(m).startswith("0:00") and _spc_playing(m), frames=1200, what="e de novo")
    assert _title(m) == "First Tune", m.text()
    assert c.tr("text_pcm_ended") not in _clock(m)
    m.press("X")                                  # off: the folder walk is back
    m.wait(lambda: _title(m) == "Second Tune" and _spc_playing(m), frames=1500, what="a próxima")
    m.press("B")
    m.wait(lambda: m.u16("window_stack_head") == 0xFFFF and not m.has(c.tr("text_spcplay")),
           frames=900, what="o browser")
    m.close()
    assert "PlayerRepeat: false" in t.read(sd, "/sd2snes/config.yml").decode()


# ---------------------------------------------------------------- .nsf

def _quiet_nsf(title: str, songs: int) -> bytes:
    """An NSF whose every song is silence (INIT mutes the APU): each one is over 3 s in."""
    hdr = bytearray(_nsf(title=title)[:0x80])
    hdr[6] = songs
    code = bytearray(0x200)
    code[0:6] = bytes([0xA9, 0x00, 0x8D, 0x15, 0x40, 0x60])   # LDA #0 / STA $4015 / RTS
    code[0x100] = 0x60                                          # PLAY: RTS
    return bytes(hdr) + bytes(code)


def _nsf_song(m) -> int:
    return m.psram(NSF_BLK + 4, 1)[0]


def _nsf_pos(m) -> int:
    return int.from_bytes(m.psram(NSF_BLK + 6, 2), "little")


def _nsf_open(m, name: str):
    m.goto("Two Games/")
    m.press("A")
    m.wait(lambda: m.has(name), what="a pasta")
    m.settle()
    m.goto(name)
    m.press("A")
    m.wait(lambda: m.psram(NSF_BLK, 2) == b"NF" and m.psram(NSF_BLK + 3, 1)[0] == PLAYING,
           what="a música tocando")


def test_nsf_silence_ends_a_song_then_the_file_then_the_folder(t):
    """Repeat off: song 1 -> song 2 of the first file -> the second file -> "End"."""
    sd = t.sd(extra={"/Two Games/A Quiet.nsf": _quiet_nsf("First", 2),
                     "/Two Games/B Quiet.nsf": _quiet_nsf("Second", 1)})
    m = t.menu(sd)
    _nsf_open(m, "A Quiet.nsf")
    assert _nsf_song(m) == 1
    assert _for_secs(m, 8.0, lambda: _nsf_song(m) == 2), "a música 2 não veio depois do silêncio"
    assert _title(m) == "First"
    assert _for_secs(m, 8.0, lambda: _title(m) == "Second"), "o próximo .nsf não veio"
    assert _for_secs(m, 8.0, lambda: c.tr("text_pcm_ended") in m.screen()[TITLE_ROW + 3]), \
        "sem 'Fim' depois do último arquivo"
    m.step(60)
    assert _title(m) == "Second"
    m.press("B")
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.settle()
    assert m.selected() == "B Quiet.nsf", m.selected()
    m.close()


def test_nsf_repeat_starts_the_same_song_again(t):
    sd = t.sd(config="---\nPlayerRepeat: true\n",
              extra={"/Two Games/A Quiet.nsf": _quiet_nsf("First", 2),
                     "/Two Games/B Quiet.nsf": _quiet_nsf("Second", 1)})
    m = t.menu(sd)
    _nsf_open(m, "A Quiet.nsf")
    m.wait(lambda: _row(m) == _want(True), what="Repetir: Lig")
    assert _for_secs(m, 6.0, lambda: _nsf_pos(m) >= 2), "o relógio não andou"
    assert _for_secs(m, 8.0, lambda: _nsf_pos(m) == 0), "a música não recomeçou"
    assert _nsf_song(m) == 1 and _title(m) == "First", (_nsf_song(m), _title(m))
    m.close()


def test_nsf_song_that_keeps_playing_never_ends(t):
    """The probe tune holds a tone forever: no silence, so no song change, Repeat or not."""
    m = t.menu(t.sd(extra={"/Two Games/Tune.nsf": _nsf()}))
    _nsf_open(m, "Tune.nsf")
    assert not _for_secs(m, 6.0, lambda: _nsf_song(m) != 1), "uma música com som mudou sozinha"
    assert _nsf_pos(m) >= 4
    m.close()
