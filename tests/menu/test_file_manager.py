"""O gerenciador de arquivos do browser: as linhas de arquivo no menu de contexto (Y), copiar /
recortar / colar com a área de transferência, renomear (com os arquivos do jogo indo junto),
nova pasta, o modo de seleção (vários de uma vez) e o visualizador de texto.

O trabalho é do módulo do cartão (fileops.bin, ligado direto no build do host); o menu só pede
e mostra. A área de transferência é do firmware: FM_CLIPINFO (mode, count) diz o que ela tem."""
import ciclone as c

CLIPINFO = 0xFFAA00
FM_SELMODE = 0x7E9400
FM_NMARK = 0x7E9402


def _clip(m):
    b = m.psram(CLIPINFO, 8)
    assert b[:2] == b"FC", f"FM_CLIPINFO sem magic: {b.hex()}"
    return b[3], b[4] | (b[5] << 8)


def _row(m, label, tries=16):
    """A barra do menu aberto até a linha `label` (só DOWN, a partir do topo)."""
    want = c.tr(label)
    for _ in range(tries):
        if want in m.bar_row():
            return
        m.press("DOWN")
        m.settle(stable=6)
    raise c.MenuError(f"sem a linha {want!r} no menu\n{m.text()}")


def _top(m, name):
    """The cursor on `name`: from the top of the list (goto only walks down)."""
    if m.selected() != name:
        m.press("L")
        m.settle(stable=6)
    m.goto(name)


def _ctx(m, name, label):
    _top(m, name)
    m.press("Y")
    m.settle()
    _row(m, label)
    m.press("A")


def _enter(m, folder):
    _top(m, folder)
    m.press("A")
    m.wait(lambda: m.list_names()[:1] == ["../"], what=f"entrar em {folder}")
    m.settle()


def test_context_has_file_rows(t):
    m = t.menu()
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    for label in ("mtext_fm_copy", "mtext_fm_cut", "mtext_fm_rename", "mtext_fm_mkdir",
                  "mtext_fm_select"):
        assert m.has(c.tr(label)), f"falta {label}\n{m.text()}"
    # the ROM's own rows are still there, before the file rows
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), m.text()
    assert not m.has(c.tr("mtext_fm_paste")), "Colar sem nada na área de transferência\n" + m.text()
    assert not m.has(c.tr("mtext_fm_view")), "Visualizar numa ROM\n" + m.text()
    _row(m, "mtext_fm_cut")                        # the description box follows the bar
    m.settle()
    assert m.has(c.tr("mdesc_fm_cut")[:30]), "sem a descrição da linha\n" + m.text()
    m.press("B")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF


def test_y_on_folder_opens_file_rows(t):
    m = t.menu()
    m.goto("Two Games/")
    m.press("Y")
    m.settle()
    assert m.has(c.tr("mtext_fm_copy")) and m.has(c.tr("mtext_fm_rename")), m.text()
    m.press("B")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF and m.u8("msu_inside") == 0


def test_copy_then_paste_into_folder(t):
    sd = t.sd()
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_copy")
    m.settle()
    assert _clip(m) == (1, 1), _clip(m)
    _enter(m, "Empty Folder/")
    _ctx(m, "../", "mtext_fm_paste")
    m.wait(lambda: "Test Game.sfc" in m.list_names(), what="a cópia aparecer")
    m.settle()
    assert _clip(m) == (1, 1), "copiar não esvazia a área de transferência"
    m.close()
    assert "Test Game.sfc" in t.listdir(sd, "/Empty Folder")
    assert t.read(sd, "/Empty Folder/Test Game.sfc") == t.read(sd, "/Test Game.sfc")


def test_cut_moves_and_empties_the_clipboard(t):
    sd = t.sd()
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_cut")
    m.settle()
    assert _clip(m) == (2, 1), _clip(m)
    _enter(m, "Empty Folder/")
    _ctx(m, "../", "mtext_fm_paste")
    m.wait(lambda: "Test Game.sfc" in m.list_names(), what="o arquivo chegar")
    m.settle()
    assert _clip(m)[1] == 0, "recortar+colar deixou a área de transferência cheia"
    m.close()
    assert "Test Game.sfc" in t.listdir(sd, "/Empty Folder")
    assert "Test Game.sfc" not in t.listdir(sd, "/")


def test_copy_into_same_folder_keeps_both(t):
    sd = t.sd()
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_copy")
    m.settle()
    _ctx(m, "Test Game.sfc", "mtext_fm_paste")
    m.wait(lambda: "Test Game (2).sfc" in m.list_names(), what="a cópia com outro nome")
    m.close()
    assert t.read(sd, "/Test Game (2).sfc") == t.read(sd, "/Test Game.sfc")


def test_folder_into_itself_is_refused(t):
    sd = t.sd()
    m = t.menu(sd)
    _ctx(m, "Two Games/", "mtext_fm_copy")
    m.settle()
    _enter(m, "Two Games/")
    _ctx(m, "../", "mtext_fm_paste")
    m.wait_text(c.tr("text_fm_err_into"), frames=600)
    m.press("A")
    m.settle()
    m.close()
    assert "Two Games" not in t.listdir(sd, "/Two Games")


def test_conflict_replace(t):
    sd = t.sd(extra={"/Empty Folder/Test Game.sfc": b"OLD" * 100})
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_copy")
    m.settle()
    _enter(m, "Empty Folder/")
    _ctx(m, "../", "mtext_fm_paste")
    m.wait_text(c.tr("text_fm_conflict"), frames=600)
    m.settle()
    _row(m, "mtext_fm_replace")
    m.press("A")
    m.wait_gone(c.tr("text_fm_conflict"), frames=600)
    m.settle()
    m.close()
    assert t.read(sd, "/Empty Folder/Test Game.sfc") == t.read(sd, "/Test Game.sfc")


def test_conflict_skip(t):
    sd = t.sd(extra={"/Empty Folder/Test Game.sfc": b"OLD" * 100})
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_copy")
    m.settle()
    _enter(m, "Empty Folder/")
    _ctx(m, "../", "mtext_fm_paste")
    m.wait_text(c.tr("text_fm_conflict"), frames=600)
    m.settle()
    _row(m, "mtext_fm_skip")
    m.press("A")
    m.wait_text(c.tr("text_fm_done"), frames=600)     # skipped: the popup with the counts
    m.press("A")
    m.settle()
    m.close()
    assert t.read(sd, "/Empty Folder/Test Game.sfc") == b"OLD" * 100


ALN = ["ABCDEFGHIJKLM", "NOPQRSTUVWXYZ", "abcdefghijklm", "nopqrstuvwxyz", "0123456789-_.,",
       "'!?()/:+=*#<>"]


def _walk(m, var, target, up, down, tries=40):
    for _ in range(tries):
        v = m.u8(var)
        if v == target:
            return
        m.press(down if v < target else up)
        m.step(4)
    raise c.MenuError(f"{var} != {target}\n{m.text()}")


def _type(m, text):
    for ch in text:
        r = next(i for i, row in enumerate(ALN) if ch in row)
        _walk(m, "ce_krow", r, "UP", "DOWN")
        _walk(m, "ce_kcol", ALN[r].index(ch), "LEFT", "RIGHT")
        m.press("A")
        m.step(4)


def test_rename_rom_takes_its_save_along(t):
    sd = t.sd(extra={"/sd2snes/saves/TE/Test Game.srm": b"\x5a" * 8192})
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_rename")
    m.wait(lambda: m.has("X:OK") and m.has("Test Game.sfc_"), what="o teclado com o nome atual")
    m.settle()
    for _ in range(5):                                 # "e.sfc"
        m.press("Y")
        m.step(4)
    _type(m, "x.sfc")
    m.press("X")
    m.wait(lambda: "Test Gamx.sfc" in m.list_names(), what="o nome novo na lista")
    m.close()
    assert "Test Gamx.sfc" in t.listdir(sd, "/")
    assert t.read(sd, "/sd2snes/saves/TE/Test Gamx.srm") == b"\x5a" * 8192, "o save não foi junto"
    assert t.read(sd, "/sd2snes/saves/TE/Test Game.srm") is None


def test_new_folder(t):
    sd = t.sd()
    m = t.menu(sd)
    _ctx(m, "Test Game.sfc", "mtext_fm_mkdir")
    m.wait(lambda: m.has("X:OK"), what="o teclado")
    m.settle()
    _type(m, "New")
    m.press("X")
    m.wait(lambda: "New/" in m.list_names(), what="a pasta nova")
    m.close()
    assert "New" in t.listdir(sd, "/")


def test_selection_mode_copies_the_marked(t):
    m = t.menu()
    _ctx(m, "Test Game.sfc", "mtext_fm_select")
    m.settle()
    assert m.u8(FM_SELMODE) == 1 and m.u16(FM_NMARK) == 1, (m.u8(FM_SELMODE), m.u16(FM_NMARK))
    _top(m, "Two Games/")
    m.press("A")                                       # marks, never opens
    m.settle()
    assert m.selected() == "Two Games/" and m.u16(FM_NMARK) == 2, m.text()
    assert m.list_names()[0] == "Empty Folder/", "o A abriu a pasta no modo de seleção"
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_copy")
    m.press("A")
    m.settle()
    assert _clip(m) == (1, 2), _clip(m)
    assert m.u8(FM_SELMODE) == 0
    # the A that picked the row must not reach the browser too (it would open the entry
    # under the cursor: here, enter the folder)
    m.step(30)
    assert m.list_names()[0] == "Empty Folder/" and m.selected() == "Two Games/", m.text()


def test_selection_mode_b_leaves(t):
    m = t.menu()
    _ctx(m, "Test Game.sfc", "mtext_fm_select")
    m.settle()
    assert m.u8(FM_SELMODE) == 1
    m.press("B")
    m.settle()
    assert m.u8(FM_SELMODE) == 0
    assert m.list_names()[0] == "Empty Folder/", "o B saiu da pasta em vez do modo"


TEXT = b"First line of the file\r\nSecond line\r\n\tTabbed\r\n" + b"".join(
    b"Line %d\r\n" % i for i in range(3, 60))


def test_view_text_file(t):
    m = t.menu(t.sd(extra={"/notes.txt": TEXT}))
    _top(m, "notes.txt")
    m.press("A")
    m.wait_text("First line of the file", frames=600)
    assert m.has("Second line"), m.text()
    for _ in range(3):
        m.press("R")                                   # a page down
        m.settle(stable=6)
    assert not m.has("First line of the file") and m.has("Line 5"), m.text()
    m.press("B")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF
    assert m.selected() == "notes.txt"
