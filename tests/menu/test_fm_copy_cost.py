"""O custo de cartão de colar um jogo grande: quantos comandos de leitura e de escrita, e quantas
vezes o fluxo do cartão é quebrado (cada quebra custa o tempo de acesso do cartão; uma escrita
interrompida ainda espera o cartão terminar). Cartão FAT32 com clusters de 32 KB, como um cartão
de dezenas de GB, uma ROM de 2 MB e os arquivos da ficha dela (clipe, áudio, guias)."""
import random
import sys

import ciclone as c
import test_file_manager as fm

sys.path.insert(0, str(c.ROOT / "tools"))
from sd_fixtures import lorom  # noqa: E402

INFO_BI = "/sd2snes/info/BI"
MB = 1024 * 1024


def _blob(n, seed):
    r = random.Random(seed)
    return bytes(r.getrandbits(8) for _ in range(n))


def _io(trace):
    """(comandos R, setores R, quebras R, comandos W, setores W, quebras W) do trace."""
    rc = rs = rb = wc = ws = wb = 0
    last = None
    for line in trace.read_text().splitlines():
        k, lba, n = line.split()
        lba, n = int(lba), int(n)
        if k == "R":
            rc += 1
            rs += n
            if last != ("R", lba):
                rb += 1
        else:
            wc += 1
            ws += n
            if last != ("W", lba):
                wb += 1
        last = (k, lba + n)
    return rc, rs, rb, wc, ws, wb


def test_paste_cost_of_a_2mb_game(t):
    big = lorom("CICLONE TEST GAME") + _blob(2 * MB - len(lorom("CICLONE TEST GAME")), 1)
    extra = {
        "/Big/Big Game.sfc": big,
        f"/sd2snes/info/BI/Big Game.yml": b'---\ntitle: "Big Game"\n',
        f"/sd2snes/info/BI/Big Game.fmv": _blob(3 * MB, 2),
        f"/sd2snes/info/BI/Big Game.man": _blob(1 * MB, 3),
    }
    sd = t.sd(extra=extra, size_mb=4000, cluster=64)
    trace = t.dir / "io.txt"
    m = t.menu(sd, env={"CICLONE_SD_IOTRACE": str(trace)})
    fm._enter(m, "Big/")
    fm._ctx(m, "Big Game.sfc", "mtext_fm_copy")
    m.settle()
    n0 = len(trace.read_text().splitlines())
    fm._ctx(m, "Big Game.sfc", "mtext_fm_paste")
    # the bar counts the game's own files: 2 MB ROM + 3 MB clip + 1 MB guide (+ the .yml)
    total = lambda: int.from_bytes(m.psram(0xFFA800 + 12, 4), "little")   # noqa: E731
    m.wait(lambda: total() >= 6 * MB, frames=3000, what="bytes_total com a ficha")
    m.wait(lambda: "Big Game (2).sfc" in m.list_names(), frames=20000, what="a cópia")
    m.settle()
    lines = trace.read_text().splitlines()[n0:]
    part = t.dir / "paste.txt"
    part.write_text("\n".join(lines) + "\n")
    rc, rs, rb, wc, ws, wb = _io(part)
    print(f"\nREAD  {rc} commands, {rs} sectors ({rs * 512 // 1024} KB), {rb} stream starts")
    print(f"WRITE {wc} commands, {ws} sectors ({ws * 512 // 1024} KB), {wb} stream starts")
    assert fm._clip(m)[1] == 0, "colar não esvaziou a área de transferência"
    m.close()
    assert t.read(sd, "/Big/Big Game (2).sfc") == big
    assert t.read(sd, f"{INFO_BI}/Big Game (2).fmv") == extra[f"{INFO_BI}/Big Game.fmv"]
    assert t.read(sd, f"{INFO_BI}/Big Game (2).man") == extra[f"{INFO_BI}/Big Game.man"]
