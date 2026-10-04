"""Teste de memória do menu (Menu > Memory test): a tela, a recusa no lugar quando o core de
teste não está no cartão, e o run de verdade, que é sempre o completo (fiação + células) e
volta pelo browser recarregado."""
import ciclone as c

MT_BLK = 0xFF0780                 # MEMTEST_BLK: 'M','T', versão, estado, flags, chips, nfind
MT_ST_NONE, MT_ST_DONE, MT_ST_NOCORE, MT_ST_RUNNING, MT_ST_SEEN = 0, 1, 2, 3, 4
MT_CI_RAN = 0x01


def _open(m):
    m.press("X")
    m.settle()
    want = c.tr("mtext_mm_memtest")
    for _ in range(12):
        if want in m.bar_row():
            break
        m.press("DOWN")
        m.step(8)
    assert want in m.bar_row(), m.text()
    m.press("A")
    m.wait_text(c.tr("text_mtl_prompt"))
    m.settle()


def test_memtest_screen_and_refusal(t):
    m = t.menu()
    _open(m)
    assert m.has(c.tr("text_mtl_none")), m.text()
    assert m.has(c.tr("text_mtl_prompt2")), m.text()
    # X não faz nada nesta tela (não há mais um modo só-fiação)
    m.press("X")
    m.settle()
    assert m.psram(MT_BLK + 3, 1)[0] == MT_ST_NONE, m.psram(MT_BLK, 8)
    assert m.has(c.tr("text_mtl_none")), m.text()
    # A sem fpga_test no cartão: a firmware recusa sem parar o SNES, a própria tela mostra
    m.press("A")
    m.wait_text(c.tr("text_mtl_nocore"), frames=1800)
    m.settle()
    assert m.psram(MT_BLK + 3, 1)[0] == MT_ST_NOCORE, m.psram(MT_BLK, 8)
    m.press("B")
    m.wait_gone(c.tr("text_mtl_prompt"))
    m.settle()
    m.close()


def test_memtest_a_runs_full_test(t):
    sd = t.sd(extra={"/sd2snes/fpga_test.bi3": b"\0" * 64})
    m = t.menu(sd)
    _open(m)
    m.press("A")
    # o console fica em reset durante o teste; o browser recarregado abre a tela com o resultado
    m.wait(lambda: m.psram(MT_BLK + 3, 1)[0] in (MT_ST_DONE, MT_ST_SEEN), frames=20000,
           what="bloco do memtest publicado")
    m.wait_text(c.tr("text_mtl_prompt"), frames=3000)
    m.settle()
    blk = m.psram(MT_BLK, 64)
    assert blk[:2] == b"MT" and blk[2] == 2, blk[:8]
    # a varredura de células rodou (ou foi pulada por falta de fiação): nunca o modo só-fiação
    assert blk[63] & MT_CI_RAN, blk.hex()
    cell = [c.tr(k) for k in ("text_mtl_cellpass", "text_mtl_cellfail", "text_mtl_cellskip")]
    assert any(m.has(s) for s in cell), m.text()
    m.press("B")
    m.wait_gone(c.tr("text_mtl_prompt"))
    m.settle()
    assert m.psram(MT_BLK + 3, 1)[0] == MT_ST_SEEN, blk[:8]
    m.close()
