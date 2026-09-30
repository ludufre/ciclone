"""Ficha do jogo com os arquivos de acompanhamento: descricao (.yml, idioma do menu e texto
completo pelo Y), capa do browser (.cov) transcodificada para a faixa, e guia (.man) aberto pelo
X nas vistas 1x e 2x (A amplia). Cobre os buffers de trabalho que o firmware usa em cada etapa (a ficha,
a capa, a leitura da descricao e o viewer compartilham uma area de rascunho): nenhuma etapa
pode ser recusada nem pisar na outra."""
import gzip
from pathlib import Path

import ciclone as c

FIX = Path(__file__).parent / "fixtures"

GAMEINFO = 0xFF7400          # SRAM_GAMEINFO_ADDR: +3 flags
GI_FLAG_COVER = 0x04
DESCEXT = 0xFF7600           # SRAM_GAMEINFO_DESCEXT_ADDR: texto completo, 0 = invalido
MAN_META = 0xFF0760          # +0 bit0 guia presente, bit2 pagina 2x pronta, +1 paginas
MAN_S1META = 0xFF0770        # +0 bit0 pagina 1x pronta

YML = (b"---\n"
       b'title: "Probe Title"\n'
       b'developer: "Probe Dev"\n'
       b'description: "English probe text"\n'
       b'description_pt: "Texto de prova em portugues ' + b"longo " * 80 + b'fim"\n')


def _cov() -> bytes:
    """.cov v4 sintetico: 2x2 sprites de 16x16, uma paleta, tiles com todos os pixels acesos."""
    w = h = 2
    hdr = bytes([ord("C"), ord("V"), 4, 0, w, h, 1, 0, 4, 0, 0, 0])
    pal = b"\x00\x00" + b"".join(((i * 0x0842) & 0x7FFF).to_bytes(2, "little") for i in range(1, 16))
    blockmap = bytes(w * h)
    tiles = bytes([0xAA, 0x55] * 8 + [0xFF, 0x0F] * 8) * ((2 * h) * 16)
    return hdr + pal + blockmap + tiles


def test_game_info_with_description_cover_and_guide(t):
    sd = t.sd(config="---\nShowGameInfo: 1\nLanguage: 1\n", extra={
        "/sd2snes/info/TE/Test Game.yml": YML,
        "/sd2snes/info/TE/Test Game.man": gzip.decompress((FIX / "probe.man.gz").read_bytes()),
        "/Test Game.cov": _cov(),
    })
    m = t.menu(sd)
    m.goto("Test Game.sfc")
    m.settle()
    m.press("A")
    m.wait(lambda: m.u16("screen_dma_disable") == 1 and m.has("Probe Title"), what="a ficha")
    m.settle()
    assert m.has("Texto de prova em portugues"), "descricao no idioma do menu\n" + m.text()
    flags = m.psram(GAMEINFO + 3, 1)[0]
    assert flags & GI_FLAG_COVER, f"capa .cov nao foi para a faixa (flags {flags:#x})\n" + m.fwlog()[-2000:]
    meta = m.psram(MAN_META, 2)
    assert meta[0] & 1 and meta[1] == 1, f"guia nao detectado (meta {meta.hex()})"

    m.press("Y")                                   # texto completo
    m.wait(lambda: m.psram(DESCEXT, 1)[0] != 0, what="descricao completa")
    m.press("B")
    m.settle()

    m.press("X")                                   # viewer do guia, 1x
    m.wait(lambda: m.psram(MAN_S1META, 1)[0] & 1, frames=1800, what="pagina 1x do guia")
    m.settle()
    m.press("A")                                   # 2x (A amplia; B volta)
    m.wait(lambda: m.psram(MAN_META, 1)[0] & 0x04, frames=1800, what="pagina 2x do guia")

    log = m.fwlog()
    assert "scratch:" not in log, log[-2000:]
    m.close()
