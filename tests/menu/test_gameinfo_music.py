""""Stop music on game info" (StopMusicOnGameInfo, snes/gimusic.a65): with the menu music
playing, opening the game info screen stops it (a warm reset, behind a fade to black) and
leaves a small S-DSP program on the S-SMP so the clip / blips stay audible; leaving brings the
SAME track back without a second reset (the program returns to the IPL on a port word and the
snapshot still staged in PSRAM is uploaded again). Off, nothing changes. Up/Down inside the
screen and a launch from it never reset again."""
import ciclone as c

SPC = (c.SD2SNES / "misc" / "menu.spc").read_bytes()
STUB_HEAD = bytes([0x8F, 0x6C, 0xF2, 0x8F, 0x60, 0xF3])   # gims_stub at ARAM $0200
GIMS_PAUSED = 0xA7
YML = b'---\ntitle: "Probe Title"\n'
BASE = "---\nShowGameInfo: 1\nEnableMenuMusic: true\nMenuMusicRandom: false\n"


def _bgm(m) -> int:
    return m.peek("snescmd", 0x2F7, 1)[0]          # BGM_STATE ($2AF7): 1 playing, 3 stub


def _resets(m) -> int:
    return m.fwlog().count("RESET requested by SNES")


def _spc_stages(m) -> int:
    return m.fwlog().count("cmd: 30\n")             # SNES_CMD_LOAD_MENU_SPC


def _menu(t, on: bool, extra: dict | None = None):
    cfg = BASE + ("StopMusicOnGameInfo: true\n" if on else "")
    ex = {"/sd2snes/info/TE/Test Game.yml": YML}
    ex.update(extra or {})
    m = t.menu(t.sd(config=cfg, misc=True, extra=ex))
    m.wait(lambda: _bgm(m) == 1, frames=1800, what="a música do menu")
    m.settle()
    return m


def _ficha(m, title="Probe Title"):
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has(title), frames=2400, what="a ficha")
    m.settle()


def _lit(m):
    m.wait(lambda: m.u8("cur_bright") == m.u8("menu_brightness") and m.u8("cur_bright") > 0,
           frames=600, what="a tela acesa")


def _aram_is_the_track(m) -> float:
    """Fraction of ARAM $1000-$EFFF equal to the staged snapshot (the song mutates a little)."""
    ram, snap = m.aram(), SPC[0x100:0x10100]
    a, b = 0x1000, 0xF000
    return sum(1 for i in range(a, b) if ram[i] == snap[i]) / (b - a)


def _trace_way_back(m, frames=600):
    """Frame by frame after the key that leaves: (cur_bright, BGM_STATE, screen_dma_disable)
    until the music plays and the screen is back at the menu level."""
    level, out = None, []
    for _ in range(frames):
        m.step(1)
        # the browser alone = no info screen (screen_dma_disable 0) and no window over it
        browser = m.u16("screen_dma_disable") == 0 and m.u16("window_stack_head") == 0xFFFF
        out.append((m.u8("cur_bright"), _bgm(m), 0 if browser else 1))
        if out[-1][1] == 1 and level is None:
            level = 0
        if level is not None and out[-1][2] == 0 and out[-1][0] == m.u8("menu_brightness") > 0:
            break
    return out


def _assert_dark_while_uploading(trace, level, where):
    """The way in, backwards: fade out (levels between 0 and the menu's), black for the whole
    upload (BGM_STATE 0 = the S-SMP at the IPL until the track runs), fade in after it."""
    up = [i for i, (_, b, _) in enumerate(trace) if b == 0]
    assert up, f"{where}: the track never went up\n{trace}"
    first, last = up[0], up[-1]
    before = [cb for cb, _, _ in trace[:first]]
    assert any(0 < cb < level for cb in before) and before[-1] == 0, f"{where}: no fade-out\n{trace}"
    assert all(cb == 0 for cb, _, _ in trace[first:last + 1]), f"{where}: lit during the upload\n{trace}"
    after = trace[last + 1:]
    assert after and all(b == 1 for _, b, _ in after), f"{where}: music not back\n{trace}"
    assert any(0 < cb < level for cb, _, _ in after) and after[-1][0] == level, f"{where}: no fade-in\n{trace}"
    # the browser is never seen lit before the music plays: what fades out is the screen
    # being left (the info screen, the Recents list), and the browser only lights up after
    assert not any(d == 0 and cb > 0 and b != 1 for cb, b, d in trace), f"{where}: the browser lit without music\n{trace}"


def test_off_nothing_changes(t):
    m = _menu(t, on=False)
    r0, s0 = _resets(m), _spc_stages(m)
    m.goto("Test Game.sfc")
    m.press("A")
    _ficha(m)
    assert _bgm(m) == 1 and _resets(m) == r0, "a música parou com a opção desligada"
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="sair da ficha")
    m.settle()
    assert _bgm(m) == 1 and _resets(m) == r0 and _spc_stages(m) == s0
    assert m.selected() == "Test Game.sfc"
    m.close()


def test_on_stops_on_open_and_brings_the_same_track_back(t):
    m = _menu(t, on=True)
    r0, s0 = _resets(m), _spc_stages(m)
    assert _aram_is_the_track(m) > 0.9
    m.goto("Test Game.sfc")
    m.press("A")
    _ficha(m)
    assert _resets(m) == r0 + 1, "abrir a ficha tem que custar exatamente um reset"
    assert _bgm(m) == 3 and m.u8("gims_state") == GIMS_PAUSED
    assert m.aram()[0x200:0x206] == STUB_HEAD, "o programa do S-DSP não está no S-SMP"
    _lit(m)                                         # o fade-in termina na ficha inteira
    assert m.has("Probe Title")
    level = m.u8("menu_brightness")
    m.shot(t.dir / "screen_ficha.png")
    m.press("B")
    trace = _trace_way_back(m)
    _assert_dark_while_uploading(trace, level, "B na ficha")
    m.settle()
    m.shot(t.dir / "screen_back.png")
    assert _resets(m) == r0 + 1, "a volta não pode resetar de novo"
    assert _spc_stages(m) == s0, "a volta tem que subir a cópia já estagiada, sem novo sorteio/leitura"
    assert _aram_is_the_track(m) > 0.9, "não é a mesma faixa"
    assert m.selected() == "Test Game.sfc" and m.u16("window_stack_head") == 0xFFFF
    _lit(m)
    m.close()


def test_up_down_inside_does_not_reset(t):
    m = _menu(t, on=True)
    m.goto("Test Game.sfc")
    m.press("A")
    _ficha(m)
    r1 = _resets(m)
    m.press("UP")                                   # MSU Game/ (a folder that opens as its game)
    _ficha(m, "msugame")
    m.press("DOWN")
    _ficha(m)
    assert _resets(m) == r1 and _bgm(m) == 3, "Cima/Baixo dentro da ficha mexeram no som"
    m.press("B")
    m.wait(lambda: _bgm(m) == 1, frames=1800, what="a música de volta")
    m.close()


def test_launch_from_the_ficha_resets_once(t):
    """The ARAM is already clean (the stop's warm reset zeroed it): no wipe on the launch."""
    m = _menu(t, on=True)
    r0 = _resets(m)
    m.goto("Test Game.sfc")
    m.press("A")
    _ficha(m)
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=900, what="o boot da ROM")
    assert _resets(m) == r0 + 1, m.fwlog()[-2000:]
    m.close()


def test_recent_list_keeps_the_silence_until_it_closes(t):
    m = _menu(t, on=True, extra={"/sd2snes/lastgame.cfg": b"/Test Game.sfc\n"})
    r0 = _resets(m)
    m.press("START")
    m.wait_text(c.tr("text_last"))
    m.press("A")
    _ficha(m)
    assert _bgm(m) == 3 and _resets(m) == r0 + 1
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 0 and m.has(c.tr("text_last")), what="a lista")
    m.settle()
    m.press("A")                                    # a second ficha from the list: no reset now
    _ficha(m)
    assert _resets(m) == r0 + 1
    m.press("B")
    m.wait(lambda: m.has(c.tr("text_last")), what="a lista")
    m.settle()
    level = m.u8("menu_brightness")
    m.shot(t.dir / "screen_list.png")
    m.press("B")                                    # the list closes -> the browser -> music
    trace = _trace_way_back(m)
    _assert_dark_while_uploading(trace, level, "lista fechada")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF, m.text()
    m.shot(t.dir / "screen_back.png")
    assert _resets(m) == r0 + 1
    m.close()


def test_the_row_in_the_browser_settings(t):
    """The row sits right under "Random music", greyed with the music off, and writes the key."""
    sd = t.sd(config="---\nEnableMenuMusic: false\n")
    m = t.menu(sd)
    for _ in range(10):
        m.press("X")
        m.settle()
        if m.has(c.tr("mtext_mm_cfg")):
            break
    for lbl in ("mtext_mm_cfg", "mtext_cfg_browser"):
        want = c.tr(lbl)
        for _ in range(30):
            if want in m.bar_row():
                break
            m.press("DOWN")
            m.step(8)
        m.press("A")
        m.settle()
    rows = m.screen()
    ri = next(i for i, r in enumerate(rows) if "Random music" in r)
    assert "Stop music on game info" in rows[ri + 1], "\n".join(rows)
    for _ in range(40):
        if "Stop music on game info" in m.bar_row():
            break
        m.press("DOWN")
        m.step(8)
    m.press("A")                                    # the on/off dialog (greying never blocks)
    m.settle()
    m.press("UP")                                   # kv_onoff is Off, On: UP goes forward
    m.settle()
    m.press("A")
    m.settle()
    m.close()
    assert b"StopMusicOnGameInfo: true" in (t.read(sd, "/sd2snes/config.yml") or b"")
