"""Patch IPS aplicado na carga: o diálogo de patches abre antes de jogar, o patch escolhido
chega à ROM na PSRAM e a entrada de Recentes guarda qual patch foi usado."""
import struct

import ciclone as c

OFS = 0x0100                      # dentro do banco 0 da ROM sintética (fora do header)
DATA = b"CICLONE-PATCH"


def _ips(ofs: int, data: bytes) -> bytes:
    return b"PATCH" + ofs.to_bytes(3, "big") + struct.pack(">H", len(data)) + data + b"EOF"


def _open_patch_dialog(m):
    m.goto("Test Game.sfc")
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1, what="a ficha")
    m.settle()
    m.press("A")                                   # Jogar -> o diálogo de patches
    m.wait_text("Fix")
    m.settle()


def test_ips_patch_is_applied_on_load(t):
    sd = t.sd(extra={"/Test Game - Fix.ips": _ips(OFS, DATA)})
    m = t.menu(sd)
    _open_patch_dialog(m)
    for _ in range(4):
        if "Fix" in m.bar_row():
            break
        m.press("DOWN")
        m.step(10)
    assert "Fix" in m.bar_row(), m.text()
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot da ROM")
    assert m.psram(OFS, len(DATA)) == DATA, m.psram(OFS, len(DATA))
    m.close()
    rec = t.read(sd, "/sd2snes/lastgame.cfg")
    assert rec.startswith(b"/Test Game.sfc\t") and b"Test Game - Fix.ips" in rec, rec


def test_original_without_patch(t):
    """A 1a linha do diálogo boota a ROM sem patch."""
    sd = t.sd(extra={"/Test Game - Fix.ips": _ips(OFS, DATA)})
    m = t.menu(sd)
    _open_patch_dialog(m)
    assert "Fix" not in m.bar_row(), m.text()
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot da ROM")
    assert m.psram(OFS, len(DATA)) != DATA
    m.close()
    rec = t.read(sd, "/sd2snes/lastgame.cfg")
    assert rec.startswith(b"/Test Game.sfc\0"), rec


def _bps(src: bytes, ofs: int, data: bytes) -> bytes:
    """BPS mínimo: SourceRead até ofs, TargetRead com os bytes novos, SourceRead do resto."""
    import zlib

    def num(n: int) -> bytes:
        out = bytearray()
        while True:
            x = n & 0x7F
            n >>= 7
            if n == 0:
                out.append(0x80 | x)
                return bytes(out)
            out.append(x)
            n -= 1

    tgt = src[:ofs] + data + src[ofs + len(data):]
    body = b"BPS1" + num(len(src)) + num(len(tgt)) + num(0)
    body += num(((ofs - 1) << 2) | 0)                          # SourceRead
    body += num(((len(data) - 1) << 2) | 1) + data             # TargetRead
    rest = len(src) - ofs - len(data)
    body += num(((rest - 1) << 2) | 0)                         # SourceRead
    body += zlib.crc32(src).to_bytes(4, "little") + zlib.crc32(tgt).to_bytes(4, "little")
    return body + zlib.crc32(body).to_bytes(4, "little")


def _pick_patch(m):
    for _ in range(4):
        if "Fix" in m.bar_row():
            return
        m.press("DOWN")
        m.step(10)
    assert "Fix" in m.bar_row(), m.text()


def test_bps_patch_is_applied_on_load(t):
    import sys
    sys.path.insert(0, str(c.ROOT / "tools"))
    from sd_fixtures import lorom
    src = lorom("CICLONE TEST GAME")
    sd = t.sd(extra={"/Test Game - Fix.bps": _bps(src, OFS, DATA)})
    m = t.menu(sd)
    _open_patch_dialog(m)
    _pick_patch(m)
    m.press("A")
    m.wait(lambda: "going to snes main loop" in m.fwlog(), frames=1800, what="o boot da ROM")
    assert m.psram(OFS, len(DATA)) == DATA, m.fwlog()[-2000:]
    m.close()


def _patch_context(m):
    """Y numa linha de patch abre o menu dela (modo de header, criar ROM patcheada)."""
    _pick_patch(m)
    m.press("Y")
    m.wait_text(c.tr("mtext_patch_header_mode"))
    m.settle()


def test_patch_header_mode_is_saved(t):
    sd = t.sd(extra={"/Test Game - Fix.ips": _ips(OFS, DATA)})
    m = t.menu(sd)
    _open_patch_dialog(m)
    _patch_context(m)
    assert c.tr("mtext_patch_header_mode") in m.bar_row(), m.text()
    m.press("A")                                   # edita o valor no lugar
    m.settle()
    want = c.tr("text_patch_hdrsel_off")
    for _ in range(4):                             # no seletor de valor, UP avança
        if want in m.bar_row():
            break
        m.press("UP")
        m.step(10)
    assert want in m.bar_row(), m.text()
    m.press("A")
    m.settle()
    m.press("B")                                   # fecha o menu da linha
    m.settle()
    m.press("B")                                   # sai do diálogo: é aqui que o sidecar é gravado
    m.settle()
    m.close()
    yml = (t.read(sd, "/sd2snes/patches/TE/Test Game.yml") or b"").decode()
    assert 'Patch: "Test Game - Fix.ips"' in yml and 'Header: "headerless"' in yml, yml


def test_create_patched_rom(t):
    """"Criar ROM patcheada" grava <patch>.sfc com o patch aplicado; o menu volta e avisa."""
    sd = t.sd(extra={"/Test Game - Fix.ips": _ips(OFS, DATA)})
    m = t.menu(sd)
    n = m.fwlog().count("SNES GO!")
    _open_patch_dialog(m)
    _patch_context(m)
    want = c.tr("mtext_patch_create_rom")
    for _ in range(4):
        if want in m.bar_row():
            break
        m.press("DOWN")
        m.step(10)
    assert want in m.bar_row(), m.text()
    m.press("A")
    m.wait(lambda: m.fwlog().count("SNES GO!") > n, frames=2400, what="o menu recarregado")
    m.wait_text(c.tr("text_patch_export_ok"), frames=1200)
    m.press("B")
    m.settle()
    m.close()
    out = t.read(sd, "/Test Game - Fix.sfc")
    assert out is not None and out[OFS:OFS + len(DATA)] == DATA, out[:0] if out else out
