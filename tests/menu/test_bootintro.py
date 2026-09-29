"""Tela de power-on ("ludufre presents", snes/bootintro.a65): so no primeiro boot do menu depois
de ligar o console, com o som tocado por um programa no S-SMP; qualquer botao encurta; a opcao
BootIntro desliga. Ao terminar, o S-SMP volta ao IPL e o boot do menu segue como sempre."""
import sys

import ciclone as c

sys.path.insert(0, str(c.SD2SNES / "snes" / "utils"))
import gen_boot_intro as gbi  # noqa: E402  (o gerador da tela: onde o logo acende, o programa do som)

ON = "---\nBootIntro: true\n"


def _logo_pixel():
    img = gbi.picture()
    px = img.load()
    return max(((x, y) for y in range(gbi.H) for x in range(gbi.W)), key=lambda p: sum(px[p]))


def _lit(m, xy):
    return sum(m.rgb(*xy)) > 400


def _browser(m):
    # WRAM is garbage while the screen runs (it comes before clear_wram): wait for a real row
    return m.u16("listdisp") < 64 and "Test Game.sfc" in m.list_names()


def _boot(t, sd):
    m = c.Menu(sd, t.dir / f"run{len(t.menus) + 1}")
    t.menus.append(m)
    m.step(2)                                   # the runner has no picture before the first frame
    return m


def test_power_on_screen_shows_and_hands_back(t):
    xy = _logo_pixel()
    spc, _, _ = gbi.chime_program()
    m = _boot(t, t.sd(config=ON))
    m.wait(lambda: _lit(m, xy), frames=300, every=1, what="o logo")
    lit_at = m.frame
    # the chime program is in ARAM and running (it echoed the first notes on port 1)
    assert m.peek("aram", gbi.BASE, len(spc)) == bytes(spc)
    m.wait(lambda: _browser(m), frames=600, what="o browser")
    assert m.frame - lit_at >= gbi_hold_frames(), m.frame - lit_at
    m.settle()
    # handed back: apu_ram_init ran after it ($0100-$03FF = $AA), the menu is alive
    assert m.peek("aram", gbi.BASE, 16) == b"\xaa" * 16
    assert "Test Game.sfc" in m.list_names()


def gbi_hold_frames():
    return 100      # BI_HOLD in bootintro.a65


def test_button_cuts_it_short(t):
    xy = _logo_pixel()
    m = _boot(t, t.sd(config=ON))
    m.wait(lambda: _lit(m, xy), frames=300, every=1, what="o logo")
    lit_at = m.frame
    m.press("A")
    m.wait(lambda: _browser(m), frames=300, what="o browser")
    assert m.frame - lit_at < 90, m.frame - lit_at     # the fade out alone takes 30
    m.settle()
    assert "Test Game.sfc" in m.list_names()


def test_off_by_option(t):
    xy = _logo_pixel()
    m = _boot(t, t.sd())                       # the suite's card: BootIntro: false
    seen = False
    for _ in range(80):
        m.step(2)
        seen |= _lit(m, xy)
        if _browser(m):
            break
    assert _browser(m) and not seen
    assert m.frame < 120, m.frame
