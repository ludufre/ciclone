#!/usr/bin/env python3
"""Gera tests/menu/fixtures/probe.man.gz: um guia .man SINTETICO (uma pagina desenhada aqui,
sem PDF nem manual de verdade) pelo encoder real do firmware, extern/sd2snes/utils/gen_man.py.

O gen_man le paginas via pdftoppm; aqui o render_pdf e trocado por uma pagina gerada na
largura pedida (faixas escuras sobre fundo claro, proporcao de pagina de manual). Precisa de
numpy + Pillow (os mesmos do gen_man); o teste so le o .gz commitado, sem essas dependencias.

  python3 tools/gen_fixture_man.py
"""
import gzip
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "extern" / "sd2snes" / "utils"))
import numpy as np   # noqa: E402
import gen_man       # noqa: E402

OUT = ROOT / "tests" / "menu" / "fixtures" / "probe.man.gz"


def page(width: int) -> np.ndarray:
    h = width * 4 // 3
    a = np.full((h, width, 3), 235, dtype=np.uint8)
    line = max(1, width // 64)
    for y in range(width // 16, h - width // 16, line * 5):
        a[y:y + line * 2, width // 16:width - width // 16 - (y * 7 % (width // 3))] = (30, 30, 60)
    return a


def fake_render(pdf_path, workdir, width):
    return [page(width)]


def main() -> None:
    gen_man.render_pdf = fake_render
    with tempfile.TemporaryDirectory() as wd:
        man = Path(wd) / "probe.man"
        gen_man.encode("synthetic.pdf", str(man), title="Probe Guide", zoom=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(gzip.compress(man.read_bytes(), mtime=0))
        print(f"{OUT}: {man.stat().st_size} B -> {OUT.stat().st_size} B")


if __name__ == "__main__":
    main()
