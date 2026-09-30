"""Tema (aplicar pelo browser, "Restaurar tema", "Restaurar tema clássico" com e sem o arquivo
no cartão) e a música do menu (escolher um .spc pelo menu de contexto, "Restaurar música").
Cada ação dessas grava o config.yml e recarrega o menu."""
import ciclone as c

THM = (c.SD2SNES / "misc" / "classic.thm").read_bytes()
SPC = (c.SD2SNES / "misc" / "menu.spc").read_bytes()


def _cfg(t, sd):
    return (t.read(sd, "/sd2snes/config.yml") or b"").decode(errors="replace")


def _pick(m, *labels):
    """Menu principal (X) e, em cada nível, a linha com o label dado. O X se repete até o
    menu abrir: logo depois de um reload com música o menu ainda está subindo o .spc."""
    for _ in range(10):
        m.press("X")
        m.settle()
        if m.has(c.tr(labels[0])):
            break
    for lbl in labels:
        want = c.tr(lbl)
        for _ in range(30):
            if want in m.bar_row():
                break
            m.press("DOWN")
            m.step(8)
        assert want in m.bar_row(), (lbl, m.text())
        m.press("A")
        m.settle()


def _reloaded(m, n):
    """O menu recarregou (mais um 'SNES GO!' da firmware) e o browser voltou."""
    m.wait(lambda: m.fwlog().count("SNES GO!") > n, frames=1800, what="o menu recarregado")
    m.wait(lambda: m.u16("listdisp") and m.list_rows(), frames=1200, what="o browser")
    m.settle()
    m.step(60)                                          # a mesma folga do t.menu: um aperto logo
                                                        # depois do boot se perde (música, capa)


def test_theme_from_the_browser(t):
    sd = t.sd(extra={"/Classic.thm": THM})
    m = t.menu(sd)
    n = m.fwlog().count("SNES GO!")
    m.goto("Classic.thm")
    m.press("A")
    _reloaded(m, n)
    assert "theme: applied /Classic.thm" in m.fwlog(), m.fwlog()[-2000:]
    assert m.selected() == "Classic.thm"               # o browser volta para o .thm
    m.close()
    assert 'SkinName: /Classic.thm' in _cfg(t, sd), _cfg(t, sd)


def test_restore_theme(t):
    sd = t.sd(config='---\nSkinName: "/Classic.thm"\n', extra={"/Classic.thm": THM})
    m = t.menu(sd)
    assert "theme: applied /Classic.thm" in m.fwlog()
    n = m.fwlog().count("SNES GO!")
    _pick(m, "mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_restoretheme")
    _reloaded(m, n)
    assert "theme: applied" not in m.fwlog().split("SNES GO!")[-2]
    m.close()
    assert 'SkinName: /Classic.thm' not in _cfg(t, sd), _cfg(t, sd)


def test_restore_classic_theme(t):
    sd = t.sd(extra={"/sd2snes/classic.thm": THM})
    m = t.menu(sd)
    n = m.fwlog().count("SNES GO!")
    _pick(m, "mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_restoreclassic")
    _reloaded(m, n)
    assert "theme: applied /sd2snes/classic.thm" in m.fwlog(), m.fwlog()[-2000:]
    m.close()
    assert 'SkinName: /sd2snes/classic.thm' in _cfg(t, sd), _cfg(t, sd)


def test_restore_classic_theme_missing_file(t):
    """Sem /sd2snes/classic.thm: popup de arquivo faltando, o menu segue vivo e nada é gravado."""
    sd = t.sd()
    m = t.menu(sd)
    n = m.fwlog().count("SNES GO!")
    _pick(m, "mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_restoreclassic")
    m.wait(lambda: m.has("classic.thm"), what="o popup de arquivo faltando")
    assert m.fwlog().count("SNES GO!") == n            # não recarregou
    m.press("B")
    m.settle()
    m.close()
    assert "classic.thm" not in _cfg(t, sd), _cfg(t, sd)


def test_set_spc_as_menu_music_and_restore(t):
    sd = t.sd(config="---\nEnableMenuMusic: false\n", extra={"/Song.spc": SPC})
    m = t.menu(sd)
    n = m.fwlog().count("SNES GO!")
    m.goto("Song.spc")
    m.press("Y")
    m.settle()
    want = c.tr("text_filesel_set_as_bgm")
    for _ in range(6):
        if want in m.bar_row():
            break
        m.press("DOWN")
        m.step(8)
    assert want in m.bar_row(), m.text()
    m.press("A")
    _reloaded(m, n)
    cfg = _cfg(t, sd)
    assert 'MenuMusicFile: /Song.spc' in cfg and "EnableMenuMusic: true" in cfg, cfg
    assert "MenuMusicRandom: false" in cfg, cfg         # escolher à mão desliga o sorteio
    n = m.fwlog().count("SNES GO!")
    _pick(m, "mtext_mm_cfg", "mtext_cfg_browser", "mtext_browser_restoremusic")
    _reloaded(m, n)
    m.close()
    cfg = _cfg(t, sd)
    assert 'MenuMusicFile: /Song.spc' not in cfg and "EnableMenuMusic: true" in cfg, cfg
