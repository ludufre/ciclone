"""Editor de cheats do menu (Cheats no menu de contexto): adicionar um cheat digitando o código
e o nome no teclado da tela, editar o nome de um existente e excluir com a confirmação. Cada
operação regrava o .yml do jogo; um cheat novo vai para o topo do arquivo.

O teclado e a lista de itens do editor são dirigidos pelo ESTADO (ce_krow/ce_kcol/ce_sel/ce_n
na WRAM), não por contagem de apertos: o teste anda até a tecla/o item e só então confirma."""
import ciclone as c

YML = "/sd2snes/cheats/TE/Test Game.yml"
CHT = (b'---\n- Name: "First"\n  Enabled: false\n  Code:\n  - "7E1F2A00"\n'
       b'- Name: "Second"\n  Enabled: false\n  Code:\n  - "7E0DBF09"\n')
HEX = ["0123456789", "ABCDEF-"]
ALN = ["ABCDEFGHIJKLM", "NOPQRSTUVWXYZ", "abcdefghijklm", "nopqrstuvwxyz", "0123456789-_.,",
       "'!?()/:+=*#<>"]


def _cheat_list(t):
    sd = t.sd(extra={YML: CHT})
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.press("Y")
    m.settle()
    m.press("DOWN")
    m.step(10)
    assert c.tr("text_filesel_context_cheats") in m.bar_row(), m.text()
    m.press("A")
    m.wait_text("First")
    m.settle()
    return sd, m


def _walk(m, var, target, up, down, tries=40):
    for _ in range(tries):
        v = m.u8(var)
        if v == target:
            return
        m.press(down if v < target else up)
        m.step(4)
    raise c.MenuError(f"{var} != {target}\n{m.text()}")


def _type(m, text, rows):
    for ch in text:
        r = next(i for i, row in enumerate(rows) if ch in row)
        _walk(m, "ce_krow", r, "UP", "DOWN")
        _walk(m, "ce_kcol", rows[r].index(ch), "LEFT", "RIGHT")
        m.press("A")
        m.step(4)


def _item(m, n):
    _walk(m, "ce_sel", n, "UP", "DOWN")


def _exit_list(t, sd, m):
    m.press("B")                                   # sai da lista (grava o .yml)
    m.settle()
    m.close()
    return t.read(sd, YML).decode()


def test_add_a_cheat(t):
    sd, m = _cheat_list(t)
    m.press("SEL")                                 # novo cheat
    m.settle()
    assert m.u8("ce_isnew") == 1
    m.press("SEL")                                 # acrescenta um código e abre o teclado hex
    m.settle()
    _type(m, "7E0DBF63", HEX)
    m.press("X")                                   # OK
    m.settle()
    assert m.u8("ce_n") == 1, m.text()
    _item(m, 0)                                    # Nome
    m.press("A")
    m.settle()
    _type(m, "Probe", ALN)
    m.press("X")
    m.settle()
    _item(m, m.u8("ce_n") + 1)                     # Salvar
    m.press("A")
    m.wait_text("Probe")
    m.settle()
    assert m.has("First") and m.has("Second")
    yml = _exit_list(t, sd, m)
    assert yml.index('Name: "Probe"') < yml.index('Name: "First"'), yml   # vai para o topo
    assert '"7E0DBF63 "' in yml, yml               # o firmware grava o código com um espaço


def test_edit_a_cheat_name(t):
    sd, m = _cheat_list(t)
    m.press("Y")                                   # edita o 1o
    m.settle()
    assert m.u8("ce_isnew") == 0
    _item(m, 0)
    m.press("A")
    m.settle()
    for _ in range(len("First")):
        m.press("Y")                               # apaga
        m.step(4)
    _type(m, "Renamed", ALN)
    m.press("X")
    m.settle()
    _item(m, m.u8("ce_n") + 1)
    m.press("A")
    m.wait_text("Renamed")
    m.settle()
    yml = _exit_list(t, sd, m)
    assert 'Name: "Renamed"' in yml and 'Name: "First"' not in yml, yml
    assert '"7E1F2A00 "' in yml, yml                 # o código do cheat editado continua lá


def test_delete_a_cheat(t):
    sd, m = _cheat_list(t)
    m.press("Y")
    m.settle()
    _item(m, m.u8("ce_n") + 2)                     # Excluir
    m.press("A")
    m.wait_text(c.tr("text_confirm_hint"))         # a confirmação (padrão: Não)
    m.settle()
    yes = c.tr("text_confirm_yes_sel")
    for _ in range(4):
        if m.has(yes):
            break
        m.press("LEFT")
        m.step(8)
    assert m.has(yes), m.text()
    m.press("A")                                   # confirma
    m.wait_gone("First")
    m.settle()
    assert m.has("Second"), m.text()
    yml = _exit_list(t, sd, m)
    assert 'Name: "First"' not in yml and 'Name: "Second"' in yml, yml
