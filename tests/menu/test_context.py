"""Menu de contexto (Y) do browser."""
import ciclone as c

ROOT = ["Empty Folder/", "MSU Game/", "Two Games/", "Test Game.sfc"]


def _open_context(m, name):
    m.goto(name)
    before = m.text()
    m.press("Y")
    m.settle()
    return before


def test_y_on_rom_opens_context_and_b_closes(t):
    m = t.menu()
    _open_context(m, "Test Game.sfc")
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), m.text()
    assert m.u16("window_stack_head") != 0xFFFF
    m.press("B")
    m.settle()
    assert not m.has(c.tr("text_filesel_context_add_to_favorites"))
    assert m.u16("window_stack_head") == 0xFFFF
    assert m.selected() == "Test Game.sfc"


def test_y_on_msu_folder_opens_rom_context(t):
    """Com OpenMsuFolders o usuário nunca fica sobre a ROM -- o Y na pasta tem que
    abrir o menu de contexto DELA, e o B tem que devolver o browser à raiz, cursor na pasta."""
    m = t.menu()
    _open_context(m, "MSU Game/")
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), \
        "Y na pasta MSU-1 não abriu o menu de contexto da ROM\n" + m.text()
    assert m.u8("msu_inside") == 1                 # entrou na pasta para achar a ROM
    m.press("B")
    m.settle()
    assert m.list_names() == ROOT, m.list_names()  # e saiu de novo
    assert m.selected() == "MSU Game/"
    assert m.u8("msu_inside") == 0
    assert m.u16("window_stack_head") == 0xFFFF


def test_y_on_plain_folder_has_only_file_rows(t):
    """Uma pasta comum não tem menu de contexto próprio: o Y mostra só as linhas do
    gerenciador de arquivos (test_file_manager.py), e não entra na pasta."""
    m = t.menu()
    _open_context(m, "Two Games/")
    assert m.has(c.tr("mtext_fm_copy")), m.text()
    assert not m.has(c.tr("text_filesel_context_add_to_favorites")), m.text()
    m.press("B")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF and m.u8("msu_inside") == 0


def test_add_msu_rom_to_favorites(t):
    sd = t.sd()
    m = t.menu(sd)
    _open_context(m, "MSU Game/")
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), \
        "Y na pasta MSU-1 não abriu o menu de contexto da ROM\n" + m.text()
    m.press("A")                                   # 1ª linha: Add to favorites
    m.settle()
    assert m.selected() == "MSU Game/" and m.u8("msu_inside") == 0, (m.selected(), m.u8("msu_inside"))
    m.close()
    fav = t.read(sd, "/sd2snes/favorites.cfg")
    assert fav is not None and b"/MSU Game/msugame.sfc" in fav, fav


def test_delete_rom_from_context(t):
    sd = t.sd()
    m = t.menu(sd)
    _open_context(m, "Test Game.sfc")
    delete = c.tr("text_filesel_context_delete_file")
    assert m.has(delete), m.text()
    for _ in range(30):                            # Delete is the menu's last row
        if delete in m.bar_row():
            break
        m.press("DOWN")
        m.settle(stable=6)
    m.press("A")
    m.wait_text(c.tr("text_confirm_delete_file"), frames=300)
    m.press("LEFT")                                # default = No; Yes fica à esquerda
    m.settle(stable=6)
    m.press("A")
    m.wait(lambda: "Test Game.sfc" not in m.list_names(), what="a ROM sumir da listagem")
    m.settle()
    assert m.list_names() == ROOT[:-1], m.list_names()
    m.close()
    assert "Test Game.sfc" not in t.listdir(sd, "/")


def test_context_mode_game_info_from_msu_folder(t):
    """ShowGameInfo 2 (Contexto): a ficha só abre pela linha "Game info" do Y -- inclusive
    para a ROM de uma pasta MSU-1 (sem isso ela fica inalcançável nesse modo)."""
    m = t.menu(t.sd(config="---\nShowGameInfo: 2\n"))
    _open_context(m, "MSU Game/")
    assert m.has(c.tr("text_filesel_context_gameinfo")), \
        "Y na pasta MSU-1 (modo Contexto) não ofereceu a ficha da ROM\n" + m.text()
    m.press("A")                                   # 1ª linha na variante _gi: Game info
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("msugame"), what="a ficha")
    m.press("B")
    m.wait(lambda: m.u16("screen_dma_disable") == 0, what="sair da ficha")
    m.settle()
    assert m.list_names() == ROOT, m.list_names()
    assert m.selected() == "MSU Game/" and m.u8("msu_inside") == 0
    assert m.u16("window_stack_head") == 0xFFFF


def test_cheats_from_msu_folder_context_returns_to_the_parent(t):
    """Y numa pasta MSU-1 -> Cheats (o jogo tem cheats) -> B volta à pasta de cima.

    Na saída da lista o menu grava os cheats e, logo depois, relê a pasta de cima. O
    "ack" que o menu escrevia em MCU_CMD depois de cada comando era $55, e o MCU o
    executava como um comando 85: se a releitura chegasse enquanto ele tratava esse 85,
    ela era apagada e o browser ficava mostrando o conteúdo da pasta. Aqui o MCU é rápido
    demais para a corrida aparecer, então o teste pega a causa: nenhum 85 no log."""
    cht = b'---\n- Name: "Probe cheat"\n  Enabled: false\n  Code:\n  - "7E1F2A00"\n'
    m = t.menu(t.sd(extra={"/sd2snes/cheats/MS/msugame.yml": cht}))
    _open_context(m, "MSU Game/")
    m.press("DOWN")
    m.step(10)
    assert m.has(c.tr("text_filesel_context_cheats")), m.text()
    m.press("A")                                   # a lista de cheats
    m.wait_text("Probe cheat")
    m.press("A")                                   # liga o cheat: a saída grava o .yml
    m.settle()
    m.press("B")
    m.settle()
    assert m.list_names() == ROOT, m.list_names()
    assert m.selected() == "MSU Game/" and m.u8("msu_inside") == 0
    log = m.fwlog()
    assert "cmd: 85" not in log, "o menu mandou o ack $55 como comando\n" + log[-2000:]
    m.close()


def _last_row_is_delete(m):
    """Down to the bottom of the (scrolling) context menu: the bar ends on Delete."""
    want = c.tr("text_filesel_context_delete_file")
    for _ in range(30):
        m.press("DOWN")
        m.step(8)
    assert want in m.bar_row(), f"the last row is not Delete\n{m.text()}"


def test_delete_is_the_last_row_in_the_browser(t):
    m = t.menu()
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    _last_row_is_delete(m)


def test_delete_is_the_last_row_in_recents_and_favorites(t):
    sd = t.sd(extra={"/sd2snes/lastgame.cfg": b"/Test Game.sfc\0",
                     "/sd2snes/favorites.cfg": b"/Test Game.sfc\0"})
    m = t.menu(sd)
    m.press("START")
    m.wait_text(c.tr("text_last"))
    m.press("Y")
    m.settle()
    _last_row_is_delete(m)
    m.press("B")
    m.settle()
    m.press("B")
    m.settle()
    m.press("SEL")
    m.wait_text(c.tr("text_favorite"))
    m.press("Y")
    m.settle()
    _last_row_is_delete(m)
