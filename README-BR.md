# Ciclone

**Português** | [English](README.md)

Ambiente de **emulação / co-simulação do firmware sd2snes+** - desenvolver e testar a firmware
(menu SNES em asm 65816 + MCU LPC1756 em C + FPGA Cyclone IV em Verilog) **num PC, sem hardware físico**.

O objetivo: você edita o firmware, roda no PC, **vê o menu numa janela e navega com o teclado** - sem
flashar cartucho nem ligar um SNES.

---

## Sumário

- [A ideia](#a-ideia)
- [Pré-requisitos](#pré-requisitos-macos)
- [Início rápido](#início-rápido)
- [Comandos prontos (`run/`)](#comandos-prontos-run)
- [Como abrir (ver o menu)](#como-abrir-ver-o-menu)
- [Como testar](#como-testar)
- [Ciclo de vida do desenvolvimento](#ciclo-de-vida-do-desenvolvimento)
- [A imagem do SD](#a-imagem-do-sd)
- [Configuração local](#configuração-local)
- [Referência de comandos](#referência-de-comandos)
- [Layout do projeto](#layout-do-projeto)
- [Status dos marcos](#status-dos-marcos)
- [Gotchas / solução de problemas](#gotchas--solução-de-problemas)
- [Licenças e créditos](#licenças-e-créditos)

---

## A ideia

A firmware são **3 processadores assíncronos** que se falam pelo buffer SNESCMD (uma BRAM dual-port
no FPGA, exposta ao SNES em `$2A00`):

```
  bsnes-plus (SNES 65816)  -->  chip "sd2snes"  -->  FPGA model  <--SPI--  firmware MCU
   roda m3nu.bin                 (no bsnes)        (seam #2)     (seam #1)  (libsd2snesfw / .im3)
```

Dois **seams plugáveis** trocam fidelidade sem reescrever nada:

- **Seam #1 - transporte SPI:** (A) firmware como **lib in-process** (rápido); (B) **`.im3` real** num
  emulador Cortex-M3 (fidelidade).
- **Seam #2 - modelo de FPGA:** (A) **comportamental** C++ (rápido); (B) **`main.v` Verilated** (RTL real).

O par **A/A** dá o loop de dev rápido; **B/B** dá fidelidade máxima. Os dois lados usam o **mesmo**
`FpgaModel` e o **mesmo** seam SPI (`ciclone_spi_txrx/select/deselect`).

---

## Pré-requisitos (macOS)

```sh
brew install qt@5 verilator unicorn sdl2
```

| Ferramenta | Para quê | Obrigatória? |
|---|---|---|
| `clang` + `make` (Xcode CLT) | tudo | sim |
| `qt@5` | buildar o core do bsnes-plus | sim |
| `unicorn` | M4 - emulador do LPC1756 que roda o `.im3` real | p/ M4 |
| `sdl2` | janela interativa (`--gui`) | p/ a janela |
| `verilator` | M3 - FPGA Verilated (RTL real) | p/ M3 |
| `python3` | converter frame PPM->PNG | p/ os screenshots |

> **Não precisa** de `arm-none-eabi-gcc` nem de `snescom` no Mac para o lado C: o C da firmware é compilado
> nativo pelo `firmware_lib/build.sh`. O **menu** (`m3nu.bin`/`igmenu.bin`, asm 65816) e o `.im3` real saem
> de um build da firmware: o seu (caem no `bin/` da árvore da firmware) ou um host de build via SSH
> (`tools/build_menu.sh`, `tools/fetch_m4fw.sh`; veja [Configuração local](#configuração-local)).

---

## Início rápido

```sh
bash tools/setup.sh        # 1. clona o bsnes-plus (branch do chip) + a árvore da firmware sd2snes
                           #    (SD2SNES_DIR=/caminho/do/seu/sd2snes faz symlink do seu checkout)
bash tools/build_menu.sh   # 2. binários do menu + mapas de símbolos (precisa de host de build, veja
                           #    Configuração local; pule se sua árvore já tem bin/m3nu.bin)
bash tools/build_all.sh    # 3. builda + testa TUDO (M0-M4). Deve terminar em "== TUDO OK =="
bash tools/make_sdimg.sh   # 4. cria build/sdcard.img (FAT32 com o menu + uma árvore de teste)
```

Depois, para **ver o menu numa janela**: `bash run/menu.sh`.

---

## Comandos prontos (`run/`)

Um script por cenário - cada um builda sozinho o que faltar:

| Comando | Cenário |
|---|---|
| `bash run/setup.sh` | 1ª vez: instala deps (brew) + prepara `extern/` (bsnes-plus + a árvore da firmware) |
| `bash run/test.sh` | builda + testa **tudo** (M0-M4) |
| `bash run/menu.sh` | **abre o menu numa janela** (firmware real) - navegue com o teclado |
| `bash run/firmware.sh [im3]` | boota o **`.im3` real** no emulador e mostra o log do firmware |
| `bash run/dev.sh` | loop de dev: recompila o firmware C e **reabre a janela** |
| `bash run/screenshot.sh [frames]` | gera e abre um screenshot do menu (headless) |
| `bash run/sd.sh [jogo.sfc]` | (re)cria a imagem do SD; opcionalmente adiciona um jogo |
| `bash run/keys.sh "<botões>" "<shots>"` | roteiro de botões headless -> PNGs em `build/shots/` |
| `bash run/test_menu.sh [-k filtro]` | **suíte automatizada do menu** (builda o menu do working tree e roda) |

---

## Como abrir (ver o menu)

### Janela interativa (recomendado)

É o **core do bsnes-plus (libsnes) numa janela SDL**, com o chip sd2snes + o **firmware REAL** numa
thread + o FpgaModel. Você navega o menu de verdade.

```sh
bash host_runner/build_gui.sh                       # compila build/host_runner_gui (precisa de sdl2)
build/host_runner_gui --gui build/sdcard.img
```

**Controles:**

| Tecla | SNES | | Tecla | SNES |
|---|---|---|---|---|
| Setas | D-pad | | Enter | Start |
| `Z` / `X` | B / A | | Shift | Select |
| `A` / `S` | Y / X | | `Q` / `W` | L / R |
| `M` | menu in-game | | `ESC` | sair |

`M` aperta o combo do menu in-game por você (o que a firmware armou para o jogo carregado - padrão
L+R+Y+←, ou o seu `IngameButtonsMenu`): quatro teclas juntas costumam não registrar num teclado. Ele segura
o combo por 20 quadros e solta; o jogo também vê esses botões, como veria num controle. Os hooks ficam
desligados nos 10 s depois que o jogo começa, como no cartucho.

> Não é o aplicativo Qt completo do bsnes-plus (com menus/debugger da UI dele) - é o **motor de
> emulação** dele numa janela, com o firmware real. É o caminho que reusa 100% a fiação testada do `--fw`.

### Screenshots (headless, sem janela)

```sh
open build/frame.png       # menu sozinho (fallback emu_mode) - gerado pelo build_all
open build/frame_fw.png    # menu dirigido pelo firmware real  - gerado pelo build_all
```

Para gerar um frame avulso:

```sh
build/host_runner_fw --fw build/sdcard.img build/out.ppm 180
python3 tools/ppm2png.py build/out.ppm build/out.png && open build/out.png
```

### Roteiro de botões (headless)

O `host_runner_fw` aceita um roteiro de entrada e várias capturas no mesmo run - dá pra reproduzir um bug
do menu sem janela e comparar dois `m3nu.bin`:

```sh
# Y numa pasta MSU-1: desce 1, aperta Y, captura antes e depois
bash run/keys.sh "120:DOWN,160:Y" "150:antes,260:depois"
# direto no runner: --keys "F:BTN[+BTN][:HOLD],..."  --shots "F:saida.ppm,..."
build/host_runner_fw --fw --keys "120:DOWN,160:Y,280:B" --shots "260:a.ppm,400:b.ppm" build/sdcard.img last.ppm 401
```

Botões: `B Y SEL START UP DOWN LEFT RIGHT A X L R`, e `MENU` para o combo armado do menu in-game (combine
com `+`; `HOLD` em quadros, default 4 - 20 para o `MENU`). O log da
firmware (printf) sai no stdout do runner. A firmware roda em tempo real numa thread e o SNES espera por ela
nos handshakes, então os quadros de um roteiro são estáveis entre runs.

### Testes automatizados do menu

`tests/menu/` é uma suíte que dirige o **menu REAL + a firmware REAL** e verifica **estado**, não pixel:
texto da tela (decodificado dos buffers de tilemap em WRAM), variáveis do menu (pelo `data.map` do mesmo
build), PSRAM/BSRAM compartilhada, log da firmware e os arquivos do cartão depois do run.

```sh
bash run/test_menu.sh                  # builda o menu do working tree no host de build (~15 s) e roda tudo
bash run/test_menu.sh -k msu -v        # filtro + log
NO_BUILD=1 bash run/test_menu.sh       # reusa build/menu
REF=HEAD bash run/test_menu.sh         # testa o MENU de um commit (git archive; a firmware C segue a do working tree)
```

Um teste é uma função `test_*(t)` num `tests/menu/test_*.py`:

```python
def test_y_on_msu_folder_opens_rom_context(t):
    m = t.menu()                                    # cartão com a árvore de teste, boota até o browser
    m.goto("MSU Game/"); m.press("Y"); m.settle()
    assert m.has(c.tr("text_filesel_context_add_to_favorites"))   # texto vem do const.a65 / lang_*.py
    m.press("B"); m.settle()
    assert m.selected() == "MSU Game/" and m.u8("msu_inside") == 0
```

API (`tests/menu/ciclone.py`): `press/hold/release/step`, `wait(pred)`/`wait_text`/`wait_gone`/`settle`
(espera por condição, nunca por quadro fixo), `screen()/text()/has()/row_of()`, `list_names()/selected()/
goto()/statusbar()`, `u8/u16/wram(símbolo)`, `psram(addr)`, `fwlog()`, `shot(png)`; `t.sd(config=...,
extra={caminho: bytes})` monta o cartão, `t.read(sd, path)`/`t.listdir(sd)` leem o que a firmware gravou,
`c.tr(label, lang)` dá o texto esperado em cada idioma. Quem falha deixa `screen*.txt`, `screen*.png`,
`fw.log` e o traceback em `build/menu-tests/<teste>/`.

Cobertura atual (23 testes, ~10 s em paralelo): navegação do browser e pastas, pastas MSU-1 (abrir como
jogo, opção desligada, ordem natural das faixas), menu de contexto (ROM, pasta MSU-1, pasta
comum, favoritar, excluir com confirmação, modo Contexto), carga de jogo (popup de core ausente com
`LOAD_NACK`, boot + Recentes), listas de Favoritos/Recentes e os 8 idiomas (texto dos dicts, sem glifo
desconhecido). Teste de regressão só vale se falha sem o fix: `REF=<commit de antes do fix>` mostra isso. A suíte
precisa dos mapas de símbolos do menu testado, por isso builda o menu ela mesma (`tools/build_menu.sh`) em
vez de usar um `m3nu.bin` de release.

**Jogos reais** (`tests/menu/test_games.py`): Super Mario World (LoROM) e Donkey Kong Country 3 (HiROM,
4 MB) são carregados pelo menu e jogados nos mappers do modelo de FPGA, com asserções pelo estado do
próprio jogo na WRAM (modo de jogo, Mario andando; DKC3 até o mapa) - e o **menu in-game** sobre o SMW:
o combo (L+R+Y+←) abre, R troca de aba, B fecha e o Mario volta a andar. Esse caminho é todo código real
(o stub de NMI da firmware em `$2A10`, o handler de savestate, o `igmenu.bin`); o que o faz funcionar é o
modelo de FPGA reproduzir o `cheat.v`: o sequestro do vetor de interrupção, o unlock do SNESCMD com a
janela linear `$C0-$FF`, os operandos de branch patcheados, a liberação no `jmp ($FFxx)` final do hook, o
hook de reset (`$2A7D`), o holdoff de 10 s, mais os shadows de registradores do `ctx.v` que o menu
restaura ao fechar. O chip do bsnes entrega a ele o que a borda do cartucho vê fora das próprias faixas
(busca de vetor, escritas no barramento, leituras de `$4016`, /RESET). A mesma maquinaria roda o resto
das funções in-game, cada uma com teste: **savestates** (Start+R salva - o handler congela o jogo no hook,
o copiador do FPGA (`dma.v`, `$2020-$2029` ou o `$D4` do MCU) prepara o espelho da WRAM, VRAM/CGRAM/OAM
são relidas do console e o MCU grava a imagem de 320 KB no cartão; Start+L a reaplica), os **gestos** que
o stub ecoa para o MCU (L+R+Start+Select reseta o jogo, L+R+Select+X volta ao menu, L+R+Start+A/B cheats
liga/desliga, L+R+Start+Y / +X hooks desligados / por 10 s), **cheats de WRAM** (código que o stub roda a
cada NMI) e **cheats de ROM** (servidos pelo FPGA na leitura). O hook de IRQ (loops de quadro só por IRQ)
e o hook exe do USB (`$2C00`) só têm cobertura no `tests/test_fpga_model.cpp`. ROM nunca entra no repositório:
aponte `CICLONE_ROMS=<pasta>` para os seus dumps (busca recursiva, casados pelo CRC32 do No-Intro); sem
ela, ou sem o dump certo, esses testes aparecem como pulados, não como falha.

**Fidelidade de tempo (importa para não ter teste instável):** a firmware roda em tempo real numa thread
e o SNES emulado roda bem mais rápido. Dois mecanismos do runner, ambos só com a firmware real:
- **Sincronia de comando** (`CICLONE_SYNC=0` desliga): enquanto o MCU processa um comando, o acesso do SNES
  a `$2A00-$2FFF` espera ele voltar ao polling - no console o MCU termina comandos curtos muito antes de
  o SNES chegar ao próximo acesso. Sem isso, 1 em 12 deletes perdia o READDIR seguinte **mesmo em tempo
  real** (o menu escreve `$55` em `MCU_CMD` como "ack", o MCU o executa como comando e ecoa `$55` =
  "pronto"; ver o trace abaixo). Só vale no mapper do menu (in-game o stub de NMI executa de `$2A00`).
- **Ritmo** (`CICLONE_SPEED`, default 4x o tempo real no `--serve`; 0 = solto): pelo relógio do SNES
  (quadro + V/H) a cada acesso à janela SNESCMD, não só por quadro.
- `CICLONE_TRACE_CMD=<arquivo>` registra com timestamp todo o tráfego `MCU_CMD`/`SNES_CMD` dos dois lados.
- `CICLONE_FIXED_TIME="AAAA-MM-DD HH:MM:SS"` congela o relógio (a suíte usa `2026-01-02 03:04:05`).

---

## Como testar

### Tudo de uma vez (o "CI")

```sh
bash tools/build_all.sh
```

Builda e roda toda a pilha verificada. Saída esperada (resumida):

```
OK: test_fpga_model
OK: build/frame.png
OK: build/frame_fw.png
OK: test_vfpga_spi
OK: test_vfpga_sim
OK: test_fxpak_info (INFO direto)
OK: test_fxpak_pty (FxPakPro sobre PTY serial)
OK: firmware REAL bootou ('SNES GO!', sram test ok) e alcançou o command loop
== TUDO OK ==
```

### O firmware REAL bootando no emulador (M4)

```sh
bash m4_unicorn/build.sh
bash tools/fetch_m4fw.sh      # traz build/m4fw/{firmware.im3, sd2snes-intermediate.elf} do host de build
build/lpc_emu build/m4fw/firmware.im3
```

Mostra o **log de UART real** do firmware até o command loop. Para ver só o log limpo:

```sh
build/lpc_emu build/m4fw/firmware.im3 2>&1 \
  | grep -vE "CIC toggle|syscon|i=[0-9]+ val="
```

Trecho do que você verá:

```
sd2snes Mk.III
  [boot] f_mount (monta FAT do SD)
file_open (/sd2snes/m3nu.bin, 01): FR_OK(0)
file_open (/sd2snes/config.yml, 01): FR_OK(0)
SNES GO!
test sram
ok
  [boot] *** menu_main_loop ALCANCADO *** (firmware no command loop!)
```

### Testes unitários isolados

```sh
build/test_fpga_model    # FpgaModel comportamental (9/9, sob AddressSanitizer)
build/test_vfpga_spi     # FPGA Verilado, lado-MCU (TEST 0xf0->0xa5 + round-trip de PSRAM)
build/test_vfpga_sim     # FPGA Verilado, both-sides (MCU escreve 0x42, SNES lê $C0:0010)
build/test_fxpak_info    # servidor FxPakPro REAL responde a um INFO
build/test_fxpak_pty     # FxPakPro sobre porta serial (PTY /dev/ttysNNN)
```

---

## Ciclo de vida do desenvolvimento

### Do fluxo de hardware para o ciclone

O loop no hardware é: **editar código -> buildar a firmware (`.im3` + `m3nu.bin`) -> copiar para o cartão SD
do cartucho -> testar num SNES físico.**

O ciclone **substitui a cópia para o SD + o SNES físico pelo PC** na iteração. O que você faz depende do que
editou:

#### Caso 1 - editou o firmware C (`src/*.c`), o mais comum

```sh
bash run/dev.sh
```

Só isso. **Sem build da firmware, sem cartão SD, sem SNES.** O `run/dev.sh` recompila os **mesmos `src/*.c`
que você editou** (o `extern/sd2snes` é symlink pro seu checkout quando configurado com `SD2SNES_DIR`)
direto pro Mac e reabre a janela em segundos. Você vê a mudança no menu na hora.

> Por que é rápido: o firmware vira código **nativo** do Mac (não ARM emulado) e fica em cache; só o
> harness recompila. Testa a **lógica** C - não o binário ARM nem os drivers reais (veja o Caso 2).

#### Caso 2 - validar o binário ARM REAL (`.im3`)

```sh
# depois do seu build da firmware (arm-none-eabi-gcc, config-mk3):
bash tools/fetch_m4fw.sh      # ou FW_OBJ_DIR=<árvore da firmware>/src/obj-mk3 para um build local
bash run/firmware.sh
```

Aqui você roda o seu **build normal da firmware** (o `.im3` real precisa do arm-gcc), mas em vez do cartão
SD + SNES, o `run/firmware.sh` **boota o `.im3` no emulador** (Unicorn). Pega bugs de init/driver sem
gravar nada. O emulador resolve os símbolos do `.elf` em runtime, então sobrevive a rebuilds (o `.elf` é
auto-derivado do `.im3`, ou passe explícito: `bash run/firmware.sh <im3>`); por isso o par tem que vir do
**mesmo** build.

#### Caso 3 - editou o menu (asm 65816, `snes/`)

```sh
bash tools/build_menu.sh      # ou o seu build da firmware (o asm precisa do snescom)
bash run/sd.sh && bash run/menu.sh
```

O menu é asm, então o `m3nu.bin` ainda sai de um build de verdade. O `run/sd.sh` põe o menu novo na imagem
do SD e o `run/menu.sh` abre a janela.

### Tradução do fluxo

| Editou | No hardware | Com o ciclone |
|---|---|---|
| Firmware C | build + cartão SD + SNES | **`bash run/dev.sh`** (segundos) |
| Validar `.im3` real | build + cartão SD + SNES | build -> **`bash run/firmware.sh`** |
| Menu asm | build + cartão SD + SNES | `tools/build_menu.sh` -> **`bash run/sd.sh` -> `bash run/menu.sh`** (ou `run/test_menu.sh`) |

### O que continua precisando do hardware

O ciclone é pra **iterar rápido**; o **sign-off final** continua sendo um build de verdade num SNES físico.
Porque:

- O **Caso 1** testa a **lógica** C (compilada pro Mac) - não o binário ARM nem os drivers reais
  (SSP / SD-nativo / USB / timers são modelados ou stub).
- O **Caso 2** testa o **binário real**, mas com os periféricos **modelados**, não o silício.

Na prática, a maioria das voltas fica no `run/dev.sh` / `run/test_menu.sh`; o hardware é pra fechar. Jogo
LoROM/HiROM comum, o menu in-game, savestates, gestos e cheats rodam (ver *Jogos reais* acima), mas não
cobre: cores de coprocessador (e as janelas de savestate deles), os espelhos de WRAM/VRAM/APU do `ctx.v`
(o savestate sobrescreve o que tira deles com leitura direta do console, então só falta a imagem da APU
no arquivo), timing de hardware nem áudio.

---

## A imagem do SD

`tools/make_sdimg.sh` cria `build/sdcard.img` (FAT32, 48 MB) com `/sd2snes/m3nu.bin` + `igmenu.bin` (o
menu e o shell in-game que a firmware carrega: o MAIS RECENTE entre o `bin/` da árvore da firmware e o
`build/menu/`; os scripts da janela recriam a imagem sozinhos quando esse menu muda) + um `fpga_base.bi3` dummy, e uma **árvore de teste**
(`tools/sd_fixtures.py`) que cobre os casos do browser:

| Entrada | Caso |
|---|---|
| `Test Game.sfc` | ROM solta (LoROM mínima, header válido; bootar dá tela preta) |
| `MSU Game/` | pasta que abre como jogo (1 ROM + `<stem>.msu` + faixas `.pcm`) |
| `Two Games/` | pasta comum (2 ROMs, mesmo com `.msu`) |
| `Empty Folder/` | pasta vazia |

Usa `hdiutil` nativo do macOS - sem mtools. Os `._*` (AppleDouble) que o macOS grava em FAT e o
`.fseventsd` são apagados antes de desmontar (o browser do menu os listaria). O `config.yml` recebe
`ResetPatch: false` quando a config dada não cita a chave: com o reset patch ligado, o hook de reset cronometra
um H-IRQ contra o `$4212` para pegar fase de clock CPU/PPU desalinhada e reseta até passar - aleatório no
console, falha garantida no timing fixo do bsnes, então todo jogo resetaria para sempre.

```sh
bash tools/make_sdimg.sh                       # gera build/sdcard.img
SIZE_MB=128 bash tools/make_sdimg.sh           # imagem maior
bash tools/make_sdimg.sh /caminho/custom.img   # outro destino
M3NU=/caminho/m3nu.bin bash tools/make_sdimg.sh build/sd_fix.img   # outro menu (ex.: um fix a comparar)
SD_CONFIG=cfg.yml bash tools/make_sdimg.sh     # config.yml inicial (ex.: ShowGameInfo: 2)
SD_FIXTURES=0 bash tools/make_sdimg.sh         # sem a árvore de teste
```

**Adicionar ROMs de jogo** (p/ testar a carga de ROM ponta-a-ponta): monte a imagem e copie `.sfc`/`.smc`:

```sh
hdiutil attach build/sdcard.img                # monta em /Volumes/SD2SNES
cp ~/roms/jogo.sfc /Volumes/SD2SNES/
hdiutil detach /Volumes/SD2SNES
```

Depois, na janela, navegue até o jogo e aperte A - o firmware real faz o handshake de carga.

---

## Configuração local

**Opcional.** Sem ela, o `tools/setup.sh` clona o fork público da firmware e o `tools/build_all.sh` roda
desde que a árvore da firmware tenha um `bin/m3nu.bin` buildado. Ela é necessária para testar o **seu
checkout** ou para usar um **host de build** para o menu + mapas de símbolos (`tools/build_menu.sh`, que o
`run/test_menu.sh` chama) e para o `.im3` real do M4 (`tools/fetch_m4fw.sh`).

A configuração fica no **`.ciclone.env`** na raiz (fora do git), lido por `tools/setup.sh`,
`tools/build_menu.sh` e `tools/fetch_m4fw.sh`. **Variável de ambiente sempre vence** o arquivo, então um
override pontual não exige editar nada: `FW_SERVER_DIR=/outra/arvore bash tools/fetch_m4fw.sh`.

Formato: um `CHAVE=valor` por linha, `#` comenta a linha inteira ou o resto dela, **sem aspas e sem expansão de `~`/`$HOME`** (o
valor é lido literal; use caminhos absolutos).

```sh
# .ciclone.env
SD2SNES_DIR=/Users/eu/src/sd2snes   # sua árvore da firmware (a pasta com src/, snes/, verilog/)
SERVER=eu@hostdebuild                # host de build via SSH com snescom/sneslink + python3 (menu) e o
                                     # build da firmware (M4)
SERVER_DIR=ciclone-menu              # pasta de trabalho no host p/ o tools/build_menu.sh (relativa = $HOME de lá)
FW_SERVER_DIR=/home/eu/sd2snes       # árvore da firmware no host onde o .im3 foi buildado
```

| Variável | Usada por | Default |
|---|---|---|
| `SD2SNES_DIR` | `setup.sh`: symlink do `extern/sd2snes` pro seu checkout | clona `SD2SNES_URL` |
| `SD2SNES_URL` | `setup.sh` | `https://github.com/ludufre/sd2snes.git` |
| `BSNES_URL`, `BSNES_BRANCH` | `setup.sh` | `ludufre/bsnes-plus`, `ciclone-sd2snes-chip` |
| `SERVER` | `build_menu.sh`, `fetch_m4fw.sh` | nenhum (eles param e avisam) |
| `SERVER_DIR` | `build_menu.sh` | `ciclone-menu` |
| `FW_SERVER_DIR`, `OBJ` | `fetch_m4fw.sh` | nenhum, `obj-mk3` |
| `FW_OBJ_DIR` | `fetch_m4fw.sh`: copia `.im3` + `.elf` de um build **local** em vez de SSH | vazio |

Os ajustes do próprio runner (`CICLONE_SYNC`, `CICLONE_SPEED`, `CICLONE_TRACE_CMD`, `CICLONE_FIXED_TIME`,
`CICLONE_MENU`) são variáveis de ambiente comuns, não vêm deste arquivo; veja
[Testes automatizados do menu](#testes-automatizados-do-menu).

---

## Referência de comandos

| Comando | O que faz | Produz |
|---|---|---|
| `bash tools/setup.sh` | clona bsnes-plus (branch do chip) + a árvore da firmware (ou symlink de `SD2SNES_DIR`) | `extern/*` |
| `bash tools/build_menu.sh` | builda o menu da árvore da firmware no host de build | `build/menu/` (bins + `.map`) |
| `bash tools/build_all.sh` | builda + testa M0-M4 | `build/*`, frames, testes |
| `bash tools/make_sdimg.sh` | cria a imagem FAT32 do SD | `build/sdcard.img` |
| `bash firmware_lib/build.sh` | firmware REAL -> lib host | `build/libsd2snesfw.a` |
| `bash host_runner/build_gui.sh` | janela interativa (SDL) | `build/host_runner_gui` |
| `bash m4_unicorn/build.sh` | emulador LPC1756 (Unicorn) | `build/lpc_emu` |
| `bash fpga_model/verilate.sh` | Verila o `main.v` (lado-MCU) | `build/vfpga/` |
| `bash fpga_model/verilate_sim.sh` | Verila `sim_top.v` (both-sides) | `build/vfpga_sim/` |
| `build/host_runner_gui --gui build/sdcard.img` | **abre a janela do menu** | - |
| `build/host_runner_fw --fw build/sdcard.img out.ppm 180` | menu headless -> frame | `out.ppm` |
| `bash tools/fetch_m4fw.sh` | traz o par `.im3`+`.elf` do host de build (ou de `FW_OBJ_DIR`) | `build/m4fw/` |
| `build/lpc_emu build/m4fw/firmware.im3` | `.im3` real boota no emulador | log UART |
| `bash run/keys.sh "<botões>" "<shots>"` | roteiro de botões headless | `build/shots/*.png` |
| `python3 tools/ppm2png.py in.ppm out.png` | PPM -> PNG | `out.png` |

---

## Layout do projeto

| Dir | Conteúdo |
|---|---|
| `extern/` | `bsnes-plus` **clonado** na branch `ciclone-sd2snes-chip` (tem o chip sd2snes); `sd2snes` = a árvore da firmware (clone, ou **symlink** pro seu checkout) |
| `run/` | um script por cenário (janela, loop de dev, screenshots, roteiro de botões, suíte do menu) |
| `host_runner/` | embute o `libsnes` do bsnes; modos headless (`--fw`) e janela (`--gui`, SDL) |
| `fpga_model/` | interface `FpgaModel` + backend comportamental (`behavioral.cpp`) + Verilated (`sim/`, `stubs/`) |
| `firmware_lib/` | build de `libsd2snesfw.a` (subconjunto de `src/*.c` do firmware p/ o host) |
| `hal_host/` | shims de HAL do firmware (clock/led/rtc/power/timer/uart/spi/diskio/usb/cdc_pty) |
| `m4_unicorn/` | emulador do LPC1756 (Cortex-M3) que roda o `.im3` real + glue p/ o FpgaModel |
| `include/` | `ciclone_seam.h` - a ABI C do seam SPI |
| `tests/` | testes (FpgaModel, Verilated SPI/sim, FxPak INFO/PTY, trace VCD); `tests/menu/` = a suíte do menu |
| `tools/` | `setup.sh`, `build_all.sh`, `build_menu.sh`, `make_sdimg.sh`, `sd_fixtures.py`, `fetch_m4fw.sh`, `ppm2png.py` |
| `renode/` | (M4 alternativo) scaffold Renode + avaliação - não usado; o Unicorn é o caminho ativo |

> **Nunca editar o `extern/sd2snes` por causa do ciclone.** Overrides de HAL/headers vencem por ordem de `-I`
> (mesmo truque do `tests/host/run.sh` da firmware). A exceção é o chip `sd2snes` no bsnes (chip novo + os
> ganchos `// CICLONE`), que vive
> **commitado na branch `ciclone-sd2snes-chip`** do fork - o `setup.sh` clona já nessa branch (não é patch local).

---

## Status dos marcos

| # | Marco | Estado | Prova |
|---|---|---|---|
| **M0** | Fundações (harness + bsnes buildam) | ok | `build_all` passos 1-3 |
| **M1** | Menu boota e desenha | ok | `build/frame.png` |
| **M2** | Firmware REAL dirige o menu (in-process) | ok | `build/frame_fw.png` |
| **M2.5** | FxPakPro sobre serial (PTY), sem USB real | ok | `test_fxpak_info` + `test_fxpak_pty` |
| **M3** | FPGA Verilated both-sides (RTL real) | ok | `test_vfpga_spi` + `test_vfpga_sim` |
| **M4** | `.im3` REAL boota no emulador + FpgaModel via seam | ok | `lpc_emu` -> `menu_main_loop` |

**Atualizado para o sd2snes+ 2.17 (menu de 3 bancos) em 28/09/2026** (menu de 3 bancos + `igmenu.bin`, ~50 `.c` da
firmware; S-RTC no modelo comportamental; roteiro de botões headless).

**M4 em detalhe:** em vez de Renode/QEMU (que não têm a família LPC176x), `m4_unicorn/lpc_emu.c` emula o
Cortex-M3 com o **Unicorn Engine** e faz hook do MMIO dos periféricos LPC. O `.im3` real boota por
completo (clock/PLL, USB, monta o FAT do `sdcard.img`, abre `m3nu.bin`+`config.yml`,
`SNES GO!`, `test sram -> ok`) e alcança o `menu_main_loop`. O SSP do firmware está ligado ao **mesmo
FpgaModel dos M2/M3** pelo seam SPI (`m4_unicorn/m4_glue.cpp`) - por isso o `test sram` passa (round-trip
de memória pelo modelo).

---

## Gotchas / solução de problemas

- **`build_all` pula o M4** -> falta `unicorn`. `brew install unicorn`.
- **`build_gui.sh` falha** -> falta `sdl2` (`brew install sdl2`) ou o `sdl2-config` não está no PATH.
- **A janela não abre / sem foco** -> rode de um Terminal com acesso a display (sessão gráfica do macOS);
  o binário não é um `.app` bundle, então pode abrir atrás de outras janelas - procure na barra.
- **M4: `FALHA resolvendo simbolos`** -> o `.elf` não casa com o `.im3`, ou o build veio *stripped*.
  Rode `bash tools/fetch_m4fw.sh` depois de cada build da firmware (traz o par do **mesmo** build).
- **`firmware_lib/build.sh` falha com `undeclared`/`undefined`** depois de atualizar o sd2snes -> um `.c`
  novo entrou no `src/` (acrescente em `FW_SRCS`) ou um define novo no `config-mk3` (espelhe em
  `hal_host/config.h`). O `main.c` só linka se todo `.c` que ele alcança estiver na lista.
- **Mudou algo em `extern/bsnes-plus/bsnes/snes/cartridge/` e nada mudou** -> a regra do
  `snes-cartridge.o` no `snes/Makefile` tinha um typo (`rwilddcard`) e não via os `.cpp` da pasta; corrigido
  na branch do chip. Numa árvore velha, `rm obj/compatibility/snes-cartridge.o`.
- **Relógio do menu `88:88:88`** -> as leituras do S-RTC (`$2800`) não chegam ao modelo: o chip do bsnes
  precisa mapear o MMIO a partir de `$2800` (não `$2A00`).
- **`extern/` vazio** -> rode `bash tools/setup.sh`.
- **Verilator não acha `altpll`/`altsyncram`** -> são providos por `fpga_model/stubs/` (o `verilate*.sh`
  já os inclui).

---

## Licenças e créditos

O ciclone linka/deriva de software GPL, então **o código do ciclone fica sob GPL v2** - o denominador
comum mais restritivo, já que bsnes-plus, o firmware do sd2snes e o Unicorn são todos GPL v2.
*Este é um resumo de boa-fé, não aconselhamento jurídico; confira antes de redistribuir.*

| Componente | Licença | Papel no ciclone | Crédito |
|---|---|---|---|
| [bsnes-plus](https://github.com/devinacker/bsnes-plus) | GPL v2 | core do SNES (`libsnes`) + o chip sd2snes | byuu/Near (bsnes) + contribuidores do bsnes-plus |
| firmware [sd2snes](https://github.com/mrehkopf/sd2snes) | GPL v2 | a firmware sob teste (fontes menu / MCU / FPGA) | Maximilian Rehkopf (ikari_01) + contribuidores; fork por ludufre |
| [Unicorn Engine](https://www.unicorn-engine.org/) | GPL v2 | M4 - emulação da CPU Cortex-M3 (`lpc_emu`) | Nguyen Anh Quynh + contribuidores |
| [SDL2](https://libsdl.org/) | zlib | janela interativa (`--gui`) | Sam Lantinga + contribuidores do SDL |
| [Verilator](https://verilator.org/) | LGPLv3 / Artistic-2.0 | M3 - Verilog->C++ (o modelo gerado é permissivo) | Wilson Snyder / Veripool |
| [Qt 5](https://www.qt.io/) | LGPLv3 | dep de build do bsnes (os binários do ciclone não linkam) | The Qt Company |
| [QUsb2snes](https://github.com/Skarsnik/QUsb2snes) | GPL v3 | referência do protocolo FxPakPro (não buildado/linkado) | Sylvain "Skarsnik" Colinet |

A integração do chip está commitada na branch `ciclone-sd2snes-chip` do fork do bsnes-plus, sob a GPL v2
dele. Por binário: `host_runner*` linkam `libsnes` + a firmware (GPL v2) + SDL2 (zlib); `lpc_emu` linka o
Unicorn (GPL v2). SDL2 (zlib) é permissivo e compatível com GPLv2.

