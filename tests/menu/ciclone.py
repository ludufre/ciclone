"""Ciclone -- harness de testes do menu do sd2snes+ (firmware REAL + menu REAL, sem hardware).

Dirige `build/host_runner_fw --serve` por um protocolo de linhas (ver host_runner/runner.cpp) e
oferece asserções por ESTADO, não por pixel:

  * texto da tela  -- decodificado dos buffers de tilemap do menu em WRAM (BG2 $7EA000 / BG1
                      $7EB000; o glifo de um caractere c é o tile 2c, colunas pares no BG2 e ímpares
                      no BG1 -- é o que o `hiprint` de snes/ui.a65 escreve);
  * variáveis      -- endereços do build/menu/*.map (o data.map do MESMO build do m3nu.bin);
  * PSRAM / BSRAM  -- a memória que MCU e SNES dividem ($C00000-$FFFFFF = offset igual);
  * log da firmware e os arquivos do cartão depois do run.

A firmware roda em tempo real numa thread; o SNES espera por ela nos handshakes. Por isso os
testes ESPERAM por condição (wait/wait_text/settle), nunca por um número fixo de quadros.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "build" / "host_runner_fw"
MENU_DIR = Path(os.environ.get("CICLONE_MENU", ROOT / "build" / "menu"))
SD2SNES = ROOT / "extern" / "sd2snes"   # a árvore da firmware (src/, snes/, verilog/)
FIXED_TIME = "2026-01-02 03:04:05"

BUTTONS = {"B": 0, "Y": 1, "SEL": 2, "START": 3, "UP": 4, "DOWN": 5, "LEFT": 6, "RIGHT": 7,
           "A": 8, "X": 9, "L": 10, "R": 11}

BG2_TILE_BUF = 0x7EA000
BG1_TILE_BUF = 0x7EB000
SCREEN_ROWS = 32   # tilemap 32x32; a barra de status fica na linha listdisp+10 = 28
SCREEN_COLS = 64
UNKNOWN = "\ufffd"   # glifo sem caractere conhecido (acento fora do ACCENTS, arte, lixo)


class MenuError(AssertionError):
    pass


# ---------------------------------------------------------------- símbolos / fonte
class Symbols:
    """name -> endereço, de todos os .map do pacote do menu (data.map = variáveis WRAM)."""

    def __init__(self, menu_dir: Path = MENU_DIR):
        self.addr: dict[str, int] = {}
        maps = sorted(menu_dir.glob("*.map"))
        if not maps:
            raise MenuError(f"sem .map em {menu_dir} -- rode tools/build_menu.sh")
        # data.map primeiro: o nome de uma variável não pode ser sombreado por um label local
        maps.sort(key=lambda p: p.name != "data.map")
        for m in maps:
            for line in m.read_text(errors="replace").splitlines():
                parts = line.split()
                if len(parts) == 2 and re.fullmatch(r"[0-9A-Fa-f]{6}", parts[0]):
                    self.addr.setdefault(parts[1], int(parts[0], 16))

    def __getitem__(self, name: str) -> int:
        try:
            return self.addr[name]
        except KeyError:
            raise MenuError(f"símbolo desconhecido: {name}") from None


def _font_decode() -> dict[int, str]:
    """código de glifo -> caractere (ASCII + os acentos/cirílico do build_const.py)."""
    dec = {c: chr(c) for c in range(32, 127)}
    try:
        sys.path.insert(0, str(SD2SNES / "snes" / "utils"))
        import build_const  # type: ignore

        dec.update(build_const.DECODE)
    except Exception:
        pass
    finally:
        sys.path.pop(0)
    return dec


FONT = _font_decode()


def encode_menu_text(s: str) -> str:
    """Texto do jeito que a tela decodificada o mostra (homoglifos viram o latino)."""
    try:
        sys.path.insert(0, str(SD2SNES / "snes" / "utils"))
        import build_const  # type: ignore

        return "".join(FONT.get(build_const.ENCODE.get(ch, ord(ch)), ch) for ch in s)
    except Exception:
        return s
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------- cartão (imagem FAT32)
def make_sd(dest: Path, config: str | None = None, fixtures: bool = True, extra: dict | None = None) -> Path:
    """Imagem do cartão com o menu do pacote. `config` = conteúdo do config.yml inicial;
    `extra` = {caminho no cartão: bytes} gravados por cima da árvore de teste."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, M3NU=str(MENU_DIR / "m3nu.bin"), IGMENU=str(MENU_DIR / "igmenu.bin"),
               SD_FIXTURES="1" if fixtures else "0")
    cfg = None
    if config is not None:
        cfg = dest.with_suffix(".config.yml")
        cfg.write_bytes(config.replace("\r\n", "\n").replace("\n", "\r\n").encode())
        env["SD_CONFIG"] = str(cfg)
    if extra:
        xdir = dest.with_suffix(".extra")
        shutil.rmtree(xdir, ignore_errors=True)
        for path, data in extra.items():
            f = xdir / path.lstrip("/")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        env["SD_EXTRA"] = str(xdir)
    subprocess.run(["bash", str(ROOT / "tools" / "make_sdimg.sh"), str(dest)], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


class MountedSD:
    """Monta a imagem só-leitura (hdiutil) para inspecionar o que a firmware gravou."""

    def __init__(self, img: Path):
        self.img = img

    def __enter__(self) -> Path:
        out = subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", str(self.img)],
                             check=True, capture_output=True, text=True).stdout
        self.dev = out.split()[0]
        mnt = [l.split("\t")[-1].strip() for l in out.splitlines() if "/Volumes/" in l]
        if not mnt:
            raise MenuError(f"não montou {self.img}: {out}")
        return Path(mnt[0])

    def __exit__(self, *exc):
        for _ in range(5):
            if subprocess.run(["hdiutil", "detach", self.dev], capture_output=True).returncode == 0:
                return
            time.sleep(0.3)


def sd_read(img: Path, path: str) -> bytes | None:
    with MountedSD(img) as mnt:
        f = mnt / path.lstrip("/")
        return f.read_bytes() if f.exists() else None


def sd_list(img: Path, path: str = "/") -> list[str]:
    with MountedSD(img) as mnt:
        d = mnt / path.lstrip("/")
        return sorted(p.name for p in d.iterdir() if not p.name.startswith("._"))


# ---------------------------------------------------------------- o console
class Menu:
    def __init__(self, sd: Path, workdir: Path, fixed_time: str = FIXED_TIME):
        if not RUNNER.exists():
            raise MenuError(f"{RUNNER} não existe -- rode tools/build_all.sh")
        self.sd, self.workdir = sd, workdir
        workdir.mkdir(parents=True, exist_ok=True)
        self.sym = Symbols()
        self.fwlog_path = workdir / "fw.log"
        env = dict(os.environ, CICLONE_FIXED_TIME=fixed_time)
        self.err = open(workdir / "runner.err", "w")
        self.proc = subprocess.Popen([str(RUNNER), "--serve", "--fwlog", str(self.fwlog_path), str(sd)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err,
                                     text=True, bufsize=1, env=env)
        line = self.proc.stdout.readline().strip()
        if line != "ready":
            raise MenuError(f"runner não subiu ({line!r}); veja {workdir / 'runner.err'}")
        self.frame = 0
        self._held = 0

    # -- protocolo
    def _cmd(self, line: str) -> str:
        if self.proc.poll() is not None:
            raise MenuError(f"runner morreu (rc={self.proc.returncode}); veja {self.workdir / 'runner.err'}")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        resp = self.proc.stdout.readline().strip()
        if not resp.startswith("ok"):
            raise MenuError(f"runner: {line!r} -> {resp!r}")
        return resp[3:]

    def close(self):
        if self.proc.poll() is None:
            try:
                self._cmd("quit")
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.err.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- tempo e botões
    def step(self, n: int = 1) -> int:
        self.frame = int(self._cmd(f"step {n}"))
        return self.frame

    def hold(self, *btns: str):
        mask = 0
        for b in btns:
            mask |= 1 << BUTTONS[b]
        self._held = mask
        self._cmd(f"buttons {mask:x}")

    def release(self):
        self.hold()

    def press(self, *btns: str, hold: int = 3, after: int = 3):
        """Aperta e solta (o menu lê o pad no NMI; 3 quadros cobrem a borda de subida)."""
        self.hold(*btns)
        self.step(hold)
        self.release()
        self.step(after)

    # -- memória
    def peek(self, space: str, addr: int, n: int) -> bytes:
        return bytes.fromhex(self._cmd(f"peek {space} {addr:x} {n:x}"))

    def _wram_index(self, addr: int | str) -> int:
        a = self.sym[addr] if isinstance(addr, str) else addr
        if not 0x7E0000 <= a <= 0x7FFFFF:
            raise MenuError(f"{addr} = ${a:06X} não é WRAM")
        return a - 0x7E0000

    def wram(self, addr: int | str, n: int = 1) -> bytes:
        return self.peek("wram", self._wram_index(addr), n)

    def u8(self, addr: int | str) -> int:
        return self.wram(addr, 1)[0]

    def u16(self, addr: int | str) -> int:
        return int.from_bytes(self.wram(addr, 2), "little")

    def psram(self, addr: int, n: int) -> bytes:
        """PSRAM; o menu enxerga $C00000-$FFFFFF no MESMO offset (BSRAM $FF... incluso)."""
        return self.peek("psram", addr & 0xFFFFFF, n)

    # -- tela
    def screen(self) -> list[str]:
        bg2 = self.wram(BG2_TILE_BUF, SCREEN_ROWS * 64)
        bg1 = self.wram(BG1_TILE_BUF, SCREEN_ROWS * 64)
        rows = []
        for y in range(SCREEN_ROWS):
            line = []
            for x in range(SCREEN_COLS):
                buf = bg2 if x % 2 == 0 else bg1
                off = y * 64 + (x & ~1)
                tile = (buf[off] | (buf[off + 1] << 8)) & 0x3FF
                c = tile >> 1 if tile < 0x200 else 0
                line.append(FONT.get(c, " " if c < 32 else UNKNOWN))
            rows.append("".join(line).rstrip())
        return rows

    def text(self) -> str:
        return "\n".join(self.screen())

    def has(self, s: str) -> bool:
        return encode_menu_text(s) in self.text()

    def row_of(self, s: str) -> int | None:
        s = encode_menu_text(s)
        for i, r in enumerate(self.screen()):
            if s in r:
                return i
        return None

    # -- esperas
    def wait(self, pred, frames: int = 900, every: int = 2, what: str = "condição"):
        start = self.frame
        while self.frame - start < frames:
            if pred():
                return
            self.step(every)
        raise MenuError(f"timeout ({frames} quadros) esperando {what}\n--- tela ---\n{self.text()}")

    def wait_text(self, s: str, frames: int = 900):
        self.wait(lambda: self.has(s), frames, what=repr(s))

    def wait_gone(self, s: str, frames: int = 900):
        self.wait(lambda: not self.has(s), frames, what=f"sumir {s!r}")

    def settle(self, stable: int = 20, frames: int = 1200):
        """Espera a tela e o cursor pararem de mudar por `stable` quadros (MCU ocioso)."""
        last, same, start = None, 0, self.frame
        while self.frame - start < frames:
            cur = (self.text(), self.u16("filesel_sel"), self.u16("window_stack_head"))
            same = same + 2 if cur == last else 0
            if same >= stable:
                return
            last = cur
            self.step(2)
        raise MenuError(f"a tela não estabilizou em {frames} quadros\n{self.text()}")

    # -- browser
    def list_rows(self) -> list[str]:
        """Linhas do browser: entre o logo e a barra de status (as que não estão vazias)."""
        rows = self.screen()
        return [r.strip() for r in rows[LIST_TOP:LIST_TOP + self.u16("listdisp")] if r.strip()]

    def list_names(self) -> list[str]:
        return [re.split(r"\s{2,}", r)[0] for r in self.list_rows()]

    def statusbar(self) -> str:
        return self.screen()[LIST_TOP - 9 + self.u16("listdisp") + 10].strip()

    def selected(self) -> str:
        """Nome da entrada sob o cursor (a linha do browser em filesel_sel), sem o '<dir>'/tamanho."""
        row = self.screen()[LIST_TOP + (self.u16("filesel_sel") & 0xFF)]
        return re.split(r"\s{2,}", row.strip())[0] if row.strip() else ""

    def goto(self, name: str, max_steps: int = 40):
        """Move o cursor até a entrada `name` no diretório corrente (só DOWN, a partir do topo)."""
        for _ in range(max_steps):
            if self.selected() == name:
                return
            self.press("DOWN")
            self.settle(stable=8)
        raise MenuError(f"não achei {name!r} no browser\n{self.text()}")

    def fwlog(self) -> str:
        return self.fwlog_path.read_text(errors="replace") if self.fwlog_path.exists() else ""

    def shot(self, path: Path):
        ppm = path.with_suffix(".ppm")
        self._cmd(f"shot {ppm}")
        subprocess.run([sys.executable, str(ROOT / "tools" / "ppm2png.py"), str(ppm), str(path)],
                       stdout=subprocess.DEVNULL, check=False)
        ppm.unlink(missing_ok=True)


LIST_TOP = 9   # 1ª linha do browser no tilemap (calibrado: logo + margem)


# ---------------------------------------------------------------- i18n
LANGS = ["en", "ptbr", "es", "de", "fr", "it", "ru", "nl"]   # ordem = índice de CFG.language


def tr(label: str, lang: str = "en") -> str:
    """Texto de um label do menu num idioma (EN do const.a65, o resto dos dicts lang_*.py)."""
    if lang != "en":
        ns: dict = {}
        exec((SD2SNES / "snes" / "utils" / f"lang_{lang}.py").read_text(), ns)
        if label in ns["TRANSLATIONS"]:
            return ns["TRANSLATIONS"][label]
    src = (SD2SNES / "snes" / "const.a65").read_text(errors="replace")
    m = re.search(rf'^{re.escape(label)}\s+\.byt\s+"((?:[^"\\]|\\.)*)"', src, re.M)
    if not m:
        raise MenuError(f"label {label} não achado no const.a65")
    return m.group(1)
