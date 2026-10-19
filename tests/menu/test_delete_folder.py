"""Excluir pasta e excluir os marcados (FM_OP_RMDIR / FM_OP_RMSEL, o módulo rmdir.bin).

A linha "Excluir pasta" no menu de contexto de uma pasta (e no do jogo de uma pasta MSU-1) e a
linha "Excluir" do modo de seleção. O módulo conta sob a janela de progresso; a janela some e a
pergunta é a caixa sim/não do menu (a mesma do "Excluir este arquivo?" / "Substituir este
save?": linhas centralizadas, "[Não]  Sim" com o Não primeiro, a dica A/B), com a pasta, o que
ela tem ("4 arquivos, 1 pasta, 257 KB": as pastas só quando há) e o aviso de que o que /sd2snes
guarda por jogo fica. "Sim" volta com a janela de progresso ("Excluindo") e apaga tudo; o que
/sd2snes guarda por jogo (saves, cheats, info) fica, porque outro jogo de mesmo nome usa o mesmo
bucket. Depois: a lista recarrega, Recentes/Favoritos perdem o jogo que estava dentro, e a área
de transferência que só apontava para o que foi apagado é esvaziada. /sd2snes e o que o sistema
lê lá dentro são recusados.

A árvore padrão do cartão (tools/sd_fixtures.py): /Two Games/ = first.sfc + second.sfc (128 KB
cada) + first.msu (16 B). Os PNGs (dlg_*.png) ficam em build/menu-tests/<teste>/."""
import re
import ciclone as c

CLIPINFO = 0xFFAA00
FM_SELMODE = 0x7E9400
FM_NMARK = 0x7E9402
TWO = {"/Two Games/sub/note.txt": b"0123456789",
       "/sd2snes/saves/FI/first.srm": b"S" * 8192,
       "/sd2snes/cheats/FI/first.yml": b"---\n",
       "/sd2snes/lastgame.cfg": b"/Two Games/first.sfc\0/Test Game.sfc\0",
       "/sd2snes/favorites.cfg": b"/Two Games/second.sfc\0"}
# a folder big enough for the removal to take a few frames (the progress window)
BIG = {f"/Big/d{i // 50}/f{i:03d}.txt": b"x" * 100 for i in range(600)}


def _clip(m):
    b = m.psram(CLIPINFO, 8)
    assert b[:2] == b"FC", f"FM_CLIPINFO sem magic: {b.hex()}"
    return b[3], b[4] | (b[5] << 8)


def _n(label, n):
    return c.tr(label).replace("#", str(n))


def _row(m, label, tries=16):
    want = c.tr(label)
    for _ in range(tries):
        if want in m.bar_row():
            return
        m.press("DOWN")
        m.settle(stable=6)
    raise c.MenuError(f"sem a linha {want!r} no menu\n{m.text()}")


def _top(m, name):
    if m.selected() != name:
        m.press("L")
        m.settle(stable=6)
    m.goto(name)


def _still(m):
    """The screen without the clock's row (it ticks)."""
    return [r for r in m.screen() if not re.search(r"\d\d:\d\d", r)]


def _no_menu_left(m):
    """Nothing of the context / selection menu the delete was picked from (it leaves the
    screen before the delete counts): only the dimmed browser behind."""
    for label in ("mtext_fm_select", "mtext_fm_selexit", "mtext_fm_rmdir", "mtext_fm_copy",
                  "mtext_fm_mkdir", "text_filesel_context_add_to_favorites"):
        assert not m.has(c.tr(label)), f"sobrou {c.tr(label)!r} do menu\n{m.text()}"


def _wait_ask(m, prompt):
    m.wait_text(c.tr(prompt), frames=900)
    m.settle()
    # the menu's yes/no box: No first, and nothing of the counting window left
    assert m.has(c.tr("text_confirm_no_sel")) and m.has(c.tr("text_confirm_yes_unsel").strip()), m.text()
    assert m.has(c.tr("text_fm_rm_note")), "sem o aviso dos arquivos de jogo\n" + m.text()
    # "B:Cancel" once: the box's hint, not the progress window's border too
    assert m.text().count(c.tr("text_fm_cancel")) == 1, "a janela de progresso ficou por baixo\n" + m.text()
    assert not m.has(c.tr("text_fm_counting")), m.text()
    _no_menu_left(m)


def _ask(m, name):
    """Y na pasta, "Excluir pasta", e a pergunta na tela."""
    _top(m, name)
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_rmdir")
    m.press("A")
    _wait_ask(m, "text_fm_rm_ask")


def _yes(m):
    m.press("RIGHT")
    m.settle(stable=6)
    assert m.has(c.tr("text_confirm_yes_sel")), m.text()
    m.press("A")


def _mark(m, *names):
    """Selection mode with `names` marked (the first through Y > Select several)."""
    _top(m, names[0])
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_select")
    m.press("A")
    m.settle()
    for n in names[1:]:
        _top(m, n)
        m.press("A")
        m.settle()
    assert m.u8(FM_SELMODE) == 1 and m.u16(FM_NMARK) == len(names), (m.u8(FM_SELMODE), m.u16(FM_NMARK))


def test_folder_context_has_delete_row(t):
    m = t.menu()
    m.goto("Two Games/")
    m.press("Y")
    m.settle()
    assert m.has(c.tr("mtext_fm_rmdir")), "pasta sem Excluir pasta\n" + m.text()
    _row(m, "mtext_fm_rmdir")
    m.settle()
    assert m.has(c.tr("mdesc_fm_rmdir")[:30]), "sem a descrição da linha\n" + m.text()
    m.press("B")
    m.settle()
    _top(m, "Test Game.sfc")
    m.press("Y")
    m.settle()
    assert not m.has(c.tr("mtext_fm_rmdir")), "Excluir pasta numa ROM\n" + m.text()
    m.press("B")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF


def test_no_keeps_the_folder(t):
    sd = t.sd(extra=TWO)
    m = t.menu(sd)
    _top(m, "Two Games/")
    m.settle()
    before = _still(m)
    _ask(m, "Two Games/")
    m.shot(t.dir / "dlg_confirm_folder.png")
    assert m.has("Two Games"), "a pergunta não diz qual pasta\n" + m.text()
    # 4 files (2 ROMs, the .msu, sub/note.txt), 1 folder, 262170 bytes rounded up
    want = f"{_n('text_fm_n_files', 4)}, {_n('text_fm_n_dir', 1)}, 257 KB"
    assert m.has(want), f"sem {want!r}\n{m.text()}"
    m.press("A")                                   # "No"
    m.wait_gone(c.tr("text_fm_rm_ask"))
    m.settle()
    assert "Two Games/" in m.list_names(), m.list_names()
    assert not m.has(c.tr("text_fm_err_cancel")), "o Não deu popup\n" + m.text()
    assert m.u16("window_stack_head") == 0xFFFF
    assert _still(m) == before, "a tela não voltou limpa\n" + m.text()
    m.shot(t.dir / "dlg_after_no.png")
    m.close()
    assert "first.sfc" in t.listdir(sd, "/Two Games")


def test_yes_deletes_only_the_tree(t):
    sd = t.sd(extra=TWO)
    m = t.menu(sd)
    _ask(m, "Two Games/")
    _yes(m)
    m.wait(lambda: "Two Games/" not in m.list_names(), what="a pasta sumir da lista")
    m.settle()
    assert m.u16("window_stack_head") == 0xFFFF
    assert "Test Game.sfc" in m.list_names()
    m.shot(t.dir / "dlg_after_yes.png")
    # Recents / Favorites lost the games that were in it (republished to the menu)
    m.press("START")
    m.settle()
    assert not m.has("first"), "Recentes ainda mostram o jogo apagado\n" + m.text()
    m.press("B")
    m.settle()
    m.close()
    assert "Two Games" not in t.listdir(sd, "/")
    # what /sd2snes keeps by game stays: another "first" elsewhere would own it too
    assert t.read(sd, "/sd2snes/saves/FI/first.srm") == b"S" * 8192
    assert t.read(sd, "/sd2snes/cheats/FI/first.yml") == b"---\n"
    assert b"Two Games" not in (t.read(sd, "/sd2snes/lastgame.cfg") or b"")
    assert b"Two Games" not in (t.read(sd, "/sd2snes/favorites.cfg") or b"")


def test_progress_window_while_it_deletes(t):
    sd = t.sd(extra=BIG)
    m = t.menu(sd)
    _ask(m, "Big/")
    assert m.has(f"{_n('text_fm_n_files', 600)}, {_n('text_fm_n_dirs', 12)}, 59 KB"), m.text()
    _yes(m)
    m.wait(lambda: m.has(c.tr("text_fm_deleting")) and m.has(c.tr("text_fm_cancel")),
           frames=600, every=1, what="a janela Excluindo")
    m.shot(t.dir / "dlg_progress.png")
    _no_menu_left(m)
    m.wait(lambda: "Big/" not in m.list_names(), what="a pasta sumir")
    m.settle()
    assert not m.has(c.tr("text_fm_deleting")) and m.u16("window_stack_head") == 0xFFFF, m.text()
    m.close()
    assert "Big" not in t.listdir(sd, "/")


def test_msu_folder_game_menu_deletes_the_folder(t):
    sd = t.sd()
    m = t.menu(sd)
    m.goto("MSU Game/")
    m.press("Y")
    m.settle()
    assert m.u8("msu_inside") == 1, "não entrou na pasta MSU-1"
    assert m.has(c.tr("text_filesel_context_add_to_favorites")), "não é o menu do jogo\n" + m.text()
    assert not m.has(c.tr("mtext_fm_copy")), "linhas de arquivo agindo na ROM\n" + m.text()
    _row(m, "mtext_fm_rmdir")
    m.press("A")
    _wait_ask(m, "text_fm_rm_ask")
    _yes(m)
    m.wait(lambda: "MSU Game/" not in m.list_names() and m.list_names()[:1] != ["../"],
           what="voltar à raiz sem a pasta")
    m.settle()
    assert m.u8("msu_inside") == 0
    assert m.u16("window_stack_head") == 0xFFFF
    m.close()
    assert "MSU Game" not in t.listdir(sd, "/")


def test_clipboard_inside_is_emptied(t):
    sd = t.sd()
    m = t.menu(sd)
    _top(m, "Two Games/")
    m.press("A")
    m.wait(lambda: m.list_names()[:1] == ["../"], what="entrar em Two Games")
    m.settle()
    m.goto("first.sfc")
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_copy")
    m.press("A")
    m.settle()
    assert _clip(m) == (1, 1), _clip(m)
    m.press("B")                                   # back to the root
    m.wait(lambda: "Two Games/" in m.list_names(), what="voltar à raiz")
    m.settle()
    _ask(m, "Two Games/")
    _yes(m)
    m.wait(lambda: "Two Games/" not in m.list_names(), what="a pasta sumir")
    m.settle()
    assert _clip(m)[1] == 0, "a área de transferência ainda aponta para a pasta apagada"


def test_sd2snes_is_refused(t):
    sd = t.sd(config="---\nShowSd2snesFolder: true\n")
    m = t.menu(sd)
    m.goto("sd2snes/")
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_rmdir")
    m.press("A")
    m.wait_text(c.tr("text_fm_err_sys"), frames=900)
    m.press("A")
    m.settle()
    assert "sd2snes/" in m.list_names()
    assert m.u16("window_stack_head") == 0xFFFF
    m.close()
    assert t.read(sd, "/sd2snes/m3nu.bin")


# ---- the selection mode ----

def test_selection_delete_asks_with_the_total(t):
    sd = t.sd(extra=TWO)
    m = t.menu(sd)
    _mark(m, "Test Game.sfc", "Two Games/")
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_sdel")
    m.press("A")
    _wait_ask(m, "text_fm_sdel_ask")
    m.shot(t.dir / "dlg_confirm_marked.png")
    # Test Game.sfc (128 KB) + the 4 files of Two Games; Two Games and its sub folder
    want = f"{_n('text_fm_n_files', 5)}, {_n('text_fm_n_dirs', 2)}, 385 KB"
    assert m.has(want), f"sem {want!r}\n{m.text()}"
    m.press("B")                                   # B = No
    m.wait_gone(c.tr("text_fm_sdel_ask"))
    m.settle()
    assert m.u8(FM_SELMODE) == 1 and m.u16(FM_NMARK) == 2, "o Não saiu do modo de seleção"
    m.close()
    assert "Two Games" in t.listdir(sd, "/") and "Test Game.sfc" in t.listdir(sd, "/")


def test_selection_delete_removes_files_and_folders(t):
    sd = t.sd(extra=TWO)
    m = t.menu(sd)
    _mark(m, "Test Game.sfc", "Two Games/")
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_sdel")
    m.press("A")
    _wait_ask(m, "text_fm_sdel_ask")
    _yes(m)
    m.wait(lambda: "Two Games/" not in m.list_names(), what="os marcados sumirem")
    m.settle()
    assert m.list_names() == ["Empty Folder/", "MSU Game/"], m.list_names()
    assert m.u8(FM_SELMODE) == 0 and m.u16(FM_NMARK) == 0, "continuou no modo de seleção"
    assert m.u16("window_stack_head") == 0xFFFF
    m.shot(t.dir / "dlg_after_marked.png")
    m.close()
    root = t.listdir(sd, "/")
    assert "Two Games" not in root and "Test Game.sfc" not in root and "Empty Folder" in root
    assert t.read(sd, "/sd2snes/saves/FI/first.srm") == b"S" * 8192
    assert b"Two Games" not in (t.read(sd, "/sd2snes/lastgame.cfg") or b"")


def test_selection_delete_refuses_the_system_folder(t):
    sd = t.sd(config="---\nShowSd2snesFolder: true\n")
    m = t.menu(sd)
    _mark(m, "Test Game.sfc", "sd2snes/")
    m.press("Y")
    m.settle()
    _row(m, "mtext_fm_sdel")
    m.press("A")
    m.wait_text(c.tr("text_fm_err_sys"), frames=900)
    m.shot(t.dir / "dlg_refused.png")
    m.press("A")
    m.settle()
    assert "sd2snes/" in m.list_names() and "Test Game.sfc" in m.list_names()
    m.close()
    assert t.read(sd, "/sd2snes/m3nu.bin") and t.read(sd, "/Test Game.sfc")
