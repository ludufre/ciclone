"""A tela de descanso: sem botão por IDLE_THRES quadros a NMI escurece o menu; um botão o traz de
volta. Com uma janela aberta (o menu de contexto do [Y]) o menu tem que voltar inteiro e seguir
respondendo ao controle."""
import ciclone as c

USER_CFG = """---
PairModeAllowed: false
VideoModeMenu: 1
VideoModeGame: 2
BSXUseUsertime: false
BSXTime: 20260610183930
R213fOverride: true
1CHIPTransientFixes: false
BrightnessLimit: 15
ShortReset2Menu: 3
EnableCheats: true
EnableIngameHook: true
EnableIngameButtons: true
EnableHookHoldoff: false
ResetPatch: true
EnableIngameSavestate: 1
LoadstateDelay: 10
EnableSavestateSlots: true
IngameButtonsSaveState: SR
IngameButtonsLoadState: SL
IngameButtonsChangeState: s
SGBEnableIngameHook: false
SGBEnableState: false
SGBVolumeBoost: 0
SGBEnhOverride: false
SGBSprIncrease: false
SGBClockFix: true
SGBBiosVersion: 1
EnableScreensaver: true
SortDirectories: true
HideExtensions: false
LEDBrightness: 0
Cx4Speed: 1
GSUSpeed: 1
MSUVolumeBoost: 0
EnableAutoSave: true
EnableMSU1AutoSave: true
ShowCovers: 1
ShowCoversInLists: true
Language: 1
EnableMenuMusic: false
EnableMenuSFX: true
SortFavorites: true
EnableCheatOverlay: true
IngameButtonsMenu: YlLR
BusCompat: false
A26VideoWidth: 0
CompCartTimeLimit: 4
SkinName: sd2snes.skin
MenuMusicFile: 
ShowGameInfo: 1
GameInfoVideo: true
GameInfoMusic: true
EnableWifi: false
MenuMusicRandom: true
MenuMusicFolder: /sd2snes/music
TextOutline: 2
TextAntiAlias: 1
AskClockOnBoot: true
OpenMsuFolders: false
ShowSd2snesFolder: false
GbcMode: 1
GbcSync: false
EnableIngamePad2: false
GbcStretch: false
OnboardingVersion: 2
OnboardingDone: true
BootIntro: true
WarnExperimental: false
BrowserIcons: true
"""

IDLE_THRES = 33000          # snes/memmap.i65
DIM = 3                     # DIM_BRIGHTNESS


def _dim(m):
    m.wait(lambda: m.u8("cur_bright") == DIM, frames=IDLE_THRES + 2000, what="a tela escurecer")


def test_context_menu_survives_the_screensaver(t):
    m = t.menu(t.sd(config="---\nEnableScreensaver: true\n"))
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    title = c.tr("text_filesel_selected_file")
    before = m.text()
    assert title in before, before
    bar0 = m.u8("bar_yl")
    _dim(m)
    m.press("DOWN")
    m.wait(lambda: m.u8("cur_bright") > DIM + 5, frames=600, what="a tela clarear")
    m.settle()
    assert m.u8("bar_yl") == bar0 + 1, f"o controle não moveu a barra\n{m.text()}"
    assert m.has(title), m.text()
    m.press("B")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF, m.text()
    m.close()


def test_context_menu_survives_the_screensaver_user_config(t):
    m = t.menu(t.sd(config=USER_CFG))
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    title = c.tr("text_filesel_selected_file", "ptbr")
    assert m.has(title), m.text()
    bar0 = m.u8("bar_yl")
    _dim(m)
    m.shot(c.ROOT / "build" / "ss_dim.png")
    m.press("DOWN")
    m.wait(lambda: m.u8("cur_bright") > DIM + 5, frames=600, what="a tela clarear")
    m.settle()
    m.shot(c.ROOT / "build" / "ss_back.png")
    assert m.u8("bar_yl") == bar0 + 1, f"o controle não moveu a barra\n{m.text()}"
    assert m.has(title), m.text()
    m.close()


def test_cgram_survives_the_screensaver_with_a_cover(t):
    from test_saves_screen import _cov
    m = t.menu(t.sd(config=USER_CFG, extra={"/Test Game.cov": _cov()}))
    m.goto("Test Game.sfc")
    m.wait(lambda: m.u8("cover_loaded") == 1, frames=600, what="a capa")
    m.settle()
    m.press("Y")
    m.settle()
    cg0 = m.peek("cgram", 2, 510)
    _dim(m)
    m.press("A")
    m.wait(lambda: m.u8("cur_bright") == 15, frames=600, what="a tela clarear")
    m.step(900)                                   # the 14 s the console lasted
    cg1 = m.peek("cgram", 2, 510)
    diff = [i for i in range(510) if cg0[i] != cg1[i]]
    assert not diff, f"{len(diff)} bytes of CGRAM changed: {[hex(i + 2) for i in diff[:20]]}"
    m.close()
