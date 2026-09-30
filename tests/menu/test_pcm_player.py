"""Tocador de .pcm do browser (uma faixa MSU-1 tocada no DAC do cartucho): A na faixa abre o
player e ela toca; A pausa e retoma; B para, solta o DAC e volta ao browser. O player lê o
estado do bloco PCMPLAY_BLK que o firmware republica sozinho."""
import ciclone as c

BLK = 0xFF07C0          # PCMPLAY_BLK: 'P','C', versão, estado, pos, total
PLAYING, PAUSED = 1, 2

# 3 s de uma onda quadrada estéreo 16-bit a 44,1 kHz, com o header MSU-1 (loop point 0)
_frame = (8000).to_bytes(2, "little", signed=True) * 2
_low = (-8000).to_bytes(2, "little", signed=True) * 2
PCM = b"MSU1" + bytes(4) + b"".join((_frame if (i // 50) & 1 else _low) for i in range(44100 * 3))


def _state(m):
    return m.psram(BLK + 3, 1)[0]


def test_pcm_play_pause_resume_stop(t):
    m = t.menu(t.sd(extra={"/Two Games/Track.pcm": PCM}))
    m.goto("Two Games/")
    m.press("A")
    m.wait(lambda: m.has("Track.pcm"), what="a pasta")
    m.settle()
    m.goto("Track.pcm")
    m.press("A")
    m.wait(lambda: m.psram(BLK, 2) == b"PC" and _state(m) == PLAYING, what="a faixa tocando")
    m.wait(lambda: m.dac_playing(), what="o DAC tocando")
    m.step(120)
    assert int.from_bytes(m.psram(BLK + 6, 2), "little") == 3          # total: 3 s
    m.press("A")                                   # pausa
    m.wait(lambda: _state(m) == PAUSED, what="a pausa")
    m.wait(lambda: not m.dac_playing(), what="o DAC parado")
    m.press("A")                                   # retoma
    m.wait(lambda: _state(m) == PLAYING and m.dac_playing(), what="a retomada")
    m.press("B")                                   # para e sai
    m.wait(lambda: not m.dac_playing(), what="o DAC solto")
    m.settle()
    assert m.selected() == "Track.pcm", m.text()
    assert m.u16("window_stack_head") == 0xFFFF
    m.close()


def test_pcm_that_is_not_msu1_shows_the_error(t):
    m = t.menu(t.sd(extra={"/Two Games/Bad.pcm": b"RIFF" + bytes(4096)}))
    m.goto("Two Games/")
    m.press("A")
    m.wait(lambda: m.has("Bad.pcm"), what="a pasta")
    m.settle()
    m.goto("Bad.pcm")
    m.press("A")
    m.wait(lambda: m.psram(BLK, 2) == b"PC" and _state(m) == 4, what="o erro de formato")  # ERR_MAGIC
    assert not m.dac_playing()
    m.press("B")
    m.settle()
    assert m.selected() == "Bad.pcm"
    m.close()


# ---- a ficha com clipe (.fmv) e a música dele (.pcm): o FMV_NEXT de quadro em quadro -------
GI = 0xFF7400                     # SRAM_GAMEINFO_ADDR: +3 flags (bit1 = FMV)
TILES = 0xCA0000                  # onde o quadro corrente é estagiado


def _fmv(nframes: int) -> bytes:
    hdr = bytearray(16)
    hdr[0:3] = b"FV\x01"
    hdr[4], hdr[5] = 12, 9                          # FMV_BOX_W, FMV_BOX_H
    hdr[7] = 12                                     # fps
    hdr[8:10] = nframes.to_bytes(2, "little")
    frames = b"".join(bytes([0x10 + i]) * 176 + bytes([0x40 + i]) * 6912 for i in range(nframes))
    return bytes(hdr) + frames


def test_game_info_plays_its_clip_and_music(t):
    sd = t.sd(extra={"/sd2snes/info/TE/Test Game.yml": b'---\ntitle: "Clip Probe"\nfmv: true\n',
                     "/sd2snes/info/TE/Test Game.fmv": _fmv(4),
                     "/sd2snes/info/TE/Test Game.pcm": PCM})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Clip Probe"), what="a ficha")
    assert m.psram(GI + 3, 1)[0] & 0x02, "clipe não estagiado"
    seen = set()
    for _ in range(60):                             # o menu pede os quadros seguintes (FMV_NEXT)
        seen.add(m.psram(TILES, 1)[0])
        if len(seen) >= 3:
            break
        m.step(10)
    assert len(seen) >= 3, f"o clipe não andou: {sorted(seen)}"
    assert "cmd: 55" in m.fwlog()                   # SNES_CMD_FMV_NEXT ($37)
    m.wait(lambda: m.dac_playing(), what="a música do clipe")
    m.press("B")                                    # sair para o browser para o clipe e a música
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="sair da ficha")
    m.wait(lambda: not m.dac_playing(), what="a música parada")
    m.close()
