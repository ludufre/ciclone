#!/usr/bin/env python3
"""Ciclone -- runner da suíte de testes do menu (sem dependências: não usa pytest).

  python3 tests/menu/run.py              # todos os test_*.py de tests/menu/
  python3 tests/menu/run.py -k msu -v    # só os que casam com 'msu', com log
  python3 tests/menu/run.py -j 1         # serial (default: até 4 em paralelo)

Cada teste é uma função `test_*(t)`; `t` dá o cartão e o console:
  sd  = t.sd(config="ShowGameInfo: 2", extra={"/X.sfc": bytes})   # imagem nova (template em cache)
  m   = t.menu(sd)                                                  # boota até o browser
Artefatos de quem falha (tela em texto, PNG, log da firmware) em build/menu-tests/<teste>/.
Pré-requisitos: tools/build_all.sh (runner) e tools/build_menu.sh (menu + .map do working tree).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import inspect
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ciclone as c  # noqa: E402

OUT = c.ROOT / "build" / "menu-tests"
_sd_lock = threading.Lock()   # hdiutil + make_sdimg serializados (montagens simultâneas brigam)


class T:
    def __init__(self, name: str, verbose: bool):
        self.name, self.verbose = name, verbose
        self.dir = OUT / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.menus: list[c.Menu] = []
        self._n = 0

    def log(self, *a):
        if self.verbose:
            print(f"    [{self.name}]", *a, flush=True)

    def sd(self, config: str | None = None, extra: dict | None = None, fixtures: bool = True) -> Path:
        """Imagem do cartão só deste teste (clone APFS de um template em cache)."""
        h = hashlib.sha1()
        h.update((c.MENU_DIR / "m3nu.bin").read_bytes())
        h.update(repr((config, fixtures, sorted((k, hashlib.sha1(v).hexdigest()) for k, v in (extra or {}).items()))).encode())
        for f in ("tools/make_sdimg.sh", "tools/sd_fixtures.py"):
            h.update((c.ROOT / f).read_bytes())
        tpl = OUT / "_templates" / f"{h.hexdigest()[:16]}.img"
        with _sd_lock:
            if not tpl.exists():
                c.make_sd(tpl.with_suffix(".tmp.img"), config=config, fixtures=fixtures, extra=extra)
                tpl.with_suffix(".tmp.img").rename(tpl)
        self._n += 1
        dst = self.dir / f"sd{self._n}.img"
        subprocess.run(["cp", "-c", str(tpl), str(dst)], check=True)
        return dst

    def menu(self, sd: Path | None = None) -> c.Menu:
        sd = sd or self.sd()
        m = c.Menu(sd, self.dir / f"run{len(self.menus) + 1}")
        self.menus.append(m)
        m.wait(lambda: m.u16("listdisp") and m.list_rows(), frames=1200, what="o browser")
        m.settle()
        # a lista aparece por volta do quadro 10, mas um aperto nos primeiros ~30 quadros
        # ainda se perde (o menu termina de subir -- música, capa). Uma pessoa nunca aperta
        # tão cedo; 1 s de folga deixa todo teste começar de um menu pronto.
        m.step(60)
        self.log("boot ok no quadro", m.frame)
        return m

    def read(self, sd: Path, path: str) -> bytes | None:
        with _sd_lock:
            return c.sd_read(sd, path)

    def listdir(self, sd: Path, path: str = "/") -> list[str]:
        with _sd_lock:
            return c.sd_list(sd, path)

    def finish(self, failed: bool):
        for i, m in enumerate(self.menus, 1):
            if failed and m.proc.poll() is None:
                try:
                    (self.dir / f"screen{i}.txt").write_text(m.text())
                    m.shot(self.dir / f"screen{i}.png")
                except Exception:
                    pass
            m.close()


def discover(pattern: str | None):
    tests = []
    for f in sorted(HERE.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith("test_") and fn.__module__ == mod.__name__:
                full = f"{f.stem}.{name}"
                if not pattern or pattern in full:
                    tests.append((full, fn, inspect.getsourcelines(fn)[1]))
    tests.sort(key=lambda t: (t[0].split(".")[0], t[2]))
    return [(n, fn) for n, fn, _ in tests]


def run_one(name, fn, verbose):
    t = T(name, verbose)
    t0 = time.time()
    failed, err = False, ""
    try:
        fn(t)
    except Exception as e:  # noqa: BLE001
        failed = True
        err = "".join(traceback.format_exception_only(type(e), e)).strip()
        (t.dir / "traceback.txt").write_text(traceback.format_exc())
    finally:
        t.finish(failed)
    return name, failed, err, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", help="só testes cujo nome contém isto")
    ap.add_argument("-v", action="store_true", help="log por teste")
    ap.add_argument("-j", type=int, default=min(4, max(1, (os.cpu_count() or 2) // 2)))
    args = ap.parse_args()

    missing = [p for p in (c.RUNNER, c.MENU_DIR / "m3nu.bin", c.MENU_DIR / "data.map") if not p.exists()]
    if missing:
        sys.exit("faltando: " + ", ".join(map(str, missing)) + "\n(rode tools/build_all.sh e tools/build_menu.sh)")
    tests = discover(args.k)
    if not tests:
        sys.exit("nenhum teste")
    rev = (c.MENU_DIR / "REV").read_text().split() if (c.MENU_DIR / "REV").exists() else ["?"]
    print(f"menu: {c.MENU_DIR} ({' '.join(rev)}) -- {len(tests)} testes, -j {args.j}")
    t0 = time.time()
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.j) as ex:
        futs = [ex.submit(run_one, n, fn, args.v) for n, fn in tests]
        for fut in cf.as_completed(futs):
            name, failed, err, dt = fut.result()
            results.append((name, failed, err))
            print(f"  {'FALHOU' if failed else 'ok    '} {name} ({dt:.1f}s)", flush=True)
            if failed:
                print("         " + err.replace("\n", "\n         "))
    nfail = sum(1 for _, f, _ in results if f)
    print(f"\n{len(results) - nfail}/{len(results)} passaram em {time.time() - t0:.0f}s"
          + (f" -- artefatos em {OUT}/<teste>/" if nfail else ""))
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
