"""Navegação básica do browser sobre a árvore de teste (tools/sd_fixtures.py)."""
import ciclone as c

ROOT = ["Empty Folder/", "MSU Game/", "Two Games/", "Test Game.sfc"]


def test_boot_lists_root(t):
    m = t.menu()
    assert m.list_names() == ROOT, m.list_names()
    assert m.selected() == "Empty Folder/"
    bar = m.statusbar()
    assert bar.startswith(c.tr("text_statusbar_keys")), bar
    assert bar.endswith("01/02/2026 03:04:05"), bar   # CICLONE_FIXED_TIME chega pelo S-RTC
    assert m.u16("window_stack_head") == 0xFFFF


def test_enter_and_leave_folder(t):
    m = t.menu()
    m.goto("Two Games/")
    m.press("A")
    m.wait(lambda: "first.sfc" in m.list_names(), what="a listagem de Two Games/")
    names = m.list_names()
    assert "second.sfc" in names, names
    assert "Test Game.sfc" not in names, names
    m.press("B")
    m.wait(lambda: m.list_names() == ROOT, what="a raiz de volta")
    m.settle()
    assert m.selected() == "Two Games/"   # o dirlog devolve o cursor onde estava


def test_empty_folder_round_trip(t):
    m = t.menu()
    m.press("A")                          # cursor já está em Empty Folder/
    m.wait(lambda: "MSU Game/" not in m.list_names(), what="entrar na pasta vazia")
    m.settle()
    assert all(n.startswith("..") for n in m.list_names()), m.list_names()
    m.press("B")
    m.wait(lambda: m.list_names() == ROOT, what="a raiz de volta")
    m.settle()
    assert m.selected() == "Empty Folder/"


def test_msu_folder_opens_game_info_and_returns(t):
    """OpenMsuFolders (default ligado): A na pasta = A na ROM dela -> ficha; B volta ao pai."""
    m = t.menu()
    m.goto("MSU Game/")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("msugame"), what="a ficha do msugame")
    assert m.u8("msu_inside") == 1
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="sair da ficha")
    m.settle()
    assert m.list_names() == ROOT, m.list_names()
    assert m.selected() == "MSU Game/"
    assert m.u8("msu_inside") == 0
    assert m.u16("window_stack_head") == 0xFFFF


def test_msu_folder_plain_when_option_off(t):
    """OpenMsuFolders: 0 -> a pasta MSU-1 abre como pasta comum, com as faixas .pcm listadas."""
    m = t.menu(t.sd(config="---\nOpenMsuFolders: false\n"))
    m.goto("MSU Game/")
    m.press("A")
    m.wait(lambda: "msugame.sfc" in m.list_names(), what="a listagem da pasta MSU-1")
    names = m.list_names()
    assert "msugame-1.pcm" in names and "msugame-10.pcm" in names, names
    # faixas no fim, em ordem natural (sort.c): -1, -2, -10
    pcm = [n for n in names if n.endswith(".pcm")]
    assert pcm == ["msugame-1.pcm", "msugame-2.pcm", "msugame-10.pcm"], pcm
    assert names.index("msugame.sfc") < names.index("msugame-1.pcm")
    assert m.u16("screen_dma_disable") == 0 and m.u8("msu_inside") == 0
