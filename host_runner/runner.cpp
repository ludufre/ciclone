// Ciclone host_runner (M1+M2.C)
// Embute o core `libsnes` do bsnes-plus. Dois modos:
//   (padrão)   roda um ROM cru (auto-detect HiROM) - verificação do M1.
//   --sd2snes  ativa o chip sd2snes: instancia o FpgaModel, pré-carrega o ROM na
//              PSRAM do modelo e serve o barramento SNES via o chip (M2.C).
// Em ambos, despeja o último frame em PPM (P6).
//
// Framebuffer (snes/video/video.cpp:81): ponteiro=ppu.output+1024, pitch FIXO 1024
// uint16/linha, pixel RGB555 0RRRRRGGGGGBBBBB.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <string>
#include <pthread.h>
#include <unistd.h>
#include <ctime>
#include "libsnes.hpp"
#include "fpga_model.h"
#include "ciclone_seam.h"

// firmware (libsd2snesfw) + lock do modelo (behavioral.cpp)
extern "C" int  ciclone_fw_main(void);
extern "C" void ciclone_set_uart_echo(int on);
extern "C" void ciclone_model_lock(void);
extern "C" void ciclone_model_unlock(void);

static std::vector<uint8_t> g_rgb;
static unsigned g_w = 0, g_h = 0;
static long g_chip_reads = 0, g_chip_writes = 0;

static void vr(const uint16_t *data, unsigned width, unsigned height) {
  g_w = width; g_h = height;
  g_rgb.resize((size_t)width * height * 3);
  for (unsigned y = 0; y < height; y++) {
    const uint16_t *row = data + (size_t)y * 1024;
    for (unsigned x = 0; x < width; x++) {
      uint16_t px = row[x];
      unsigned r5 = (px >> 10) & 0x1f, g5 = (px >> 5) & 0x1f, b5 = px & 0x1f;
      size_t o = ((size_t)y * width + x) * 3;
      g_rgb[o+0] = (uint8_t)((r5 << 3) | (r5 >> 2));
      g_rgb[o+1] = (uint8_t)((g5 << 3) | (g5 >> 2));
      g_rgb[o+2] = (uint8_t)((b5 << 3) | (b5 >> 2));
    }
  }
}
static void ipoll(void) {}
static int16_t g_buttons[16] = {0};   // estado dos botões (atualizado pelo SDL no modo --gui)
// The in-game menu combo pressed by one key (the window's M, `MENU` in --keys): four buttons at
// once on a keyboard often do not register (key rollover). Held for MENU_HOLD frames, then
// released: the savestate handler opens the menu on the edge into "all held", but over SMW it
// took 7 frames of holding before it did (6 never opened it), hence the margin.
static uint16_t g_menu_mask = 0;
static int g_menu_hold = 0;
constexpr int MENU_HOLD = 20;
static int16_t istate(bool, unsigned, unsigned, unsigned id) {
  if (id >= 16) return 0;
  return g_buttons[id] || (g_menu_hold > 0 && (g_menu_mask >> id & 1));
}
// The combo the firmware armed for the loaded game (MENU_COMBO $FF0704, SNES pad-register bit
// order, valid only against ~combo at $FF0706 -- the same check ss_init makes), else the default
// L+R+Y+Left ($4230). Pad-register bit 15-i is libsnes id i. Returned as a libsnes id mask.
static uint16_t menu_combo_mask() {
  uint16_t combo = 0x4230;
  if (ciclone::FpgaModel *m = ciclone::active_model())
    if (const uint8_t *ps = m->psram_ptr()) {
      uint16_t c = ps[0xFF0704] | ps[0xFF0705] << 8, inv = ps[0xFF0706] | ps[0xFF0707] << 8;
      if (c && (c ^ inv) == 0xFFFF) combo = c;
    }
  uint16_t mask = 0;
  for (int i = 0; i < 12; i++) if (combo & (0x8000 >> i)) mask |= (uint16_t)(1u << i);
  return mask;
}
static void press_menu_combo() { g_menu_mask = menu_combo_mask(); g_menu_hold = MENU_HOLD; }
// audio: the window plays the S-SMP's output (the menu's music) mixed with the cartridge's
// DAC as far as the FPGA model produces it (the menu's sound effects: FpgaModel::sfx_samples);
// the headless modes drop it.
static bool g_audio_on = false;
static std::vector<int16_t> g_audio;
static void asample(uint16_t l, uint16_t r) {
  if (!g_audio_on) return;
  g_audio.push_back((int16_t)l); g_audio.push_back((int16_t)r);
}

// Ritmo (modo --serve): a firmware roda em tempo real e o SNES emulado, solto, roda dezenas de
// vezes mais rápido -- o tempo do SNES encolhe em relação ao do MCU e abrem raças de handshake
// que no console não existem (ex.: o READDIR logo após um delete cair na janela em que o MCU
// zera o MCU_CMD; no console o pop_window entre os dois leva ~4,5 ms). Por isso o ritmo segue o
// RELÓGIO DO SNES (quadros + posição V/H do feixe) e é aplicado a cada acesso do SNES à janela
// $2800-$2FFF -- o único canal por onde o MCU enxerga o SNES -- e no fim de cada quadro.
// Pacing só por quadro NÃO basta: dentro do quadro a emulação corre em rajada.
// CICLONE_SPEED = múltiplo do tempo real (default 4; 0 = sem limite).
extern "C" unsigned ciclone_snes_frame_pos(void);
static double g_speed = 0;          // 0 até o serve_loop ligar (gui/headless ficam sem ritmo)
static long g_frame = 0;
static double now_s() { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec + ts.tv_nsec * 1e-9; }
static void pace(double frames_done) {
  static double base_wall = 0, base_snes = 0;
  if (g_speed <= 0) return;
  const double snes_t = frames_done / 60.0988;           // segundos de SNES
  const double t = now_s();
  double target = base_wall + (snes_t - base_snes) / g_speed;
  if (base_wall == 0 || t - target > 0.25) { base_wall = t; base_snes = snes_t; return; }  // atrasados: rebase
  if (target > t) { struct timespec rq = {0, (long)((target - t) * 1e9)}; nanosleep(&rq, nullptr); }
}
// Sincronia de comando (modo --serve, CICLONE_SYNC=0 desliga): enquanto o MCU está no meio de
// um comando, o acesso do SNES à janela SNESCMD ($2A00-$2FFF) ESPERA o MCU voltar ao polling.
// No console o MCU (96 MHz) conclui um comando curto em dezenas de µs, bem antes de o SNES
// chegar ao próximo acesso; no host a thread do MCU pode perder a vez por milissegundos e o
// protocolo -- que depende desse "MCU sempre ganha" (o menu escreve $55 em MCU_CMD como ack, o
// MCU o executa como comando e ecoa $55 = "pronto") -- quebrava: medido, 1 em 12 deletes perdia
// o READDIR seguinte mesmo em tempo real. Comando longo (load, READDIR grande) só segura o SNES
// onde ele já estaria esperando; teto de 3 s para nunca travar o harness.
extern "C" int ciclone_mcu_busy(void);
static bool g_sync = false;
static inline void pace_chip(uint32_t addr) {
  if (!(addr & 0x400000) && (addr & 0xF800) == 0x2800) {
    // só no MENU (mapper 7): in-game o MCU sai do laço do menu (fica "ocupado" para sempre) e
    // o stub de NMI dos hooks EXECUTA de dentro de $2A00 -- cada busca de opcode esperaria.
    static bool gave_up = false;
    if (g_sync && (addr & 0xFE00) != 0x2800) {
      ciclone::FpgaModel *m = ciclone::active_model();
      bool busy = m && m->mapper() == 7 && ciclone_mcu_busy();
      if (!busy) gave_up = false;
      else if (!gave_up) {
        double until = now_s() + 3.0;
        while (ciclone_mcu_busy() && m->mapper() == 7 && now_s() < until) { struct timespec rq = {0, 20000}; nanosleep(&rq, nullptr); }
        gave_up = ciclone_mcu_busy();   // comando que não volta (load): não espera de novo até ele voltar
      }
    }
    if (g_speed > 0) pace(g_frame + ciclone_snes_frame_pos() / (1364.0 * 262.0));
  }
}
// The firmware's SNES reset line (hal_host misc_stubs.c): held = the CPU does not run,
// released = reset the console, which re-reads the vectors from whatever the MCU just
// loaded into PSRAM (a menu reload, the tour ROM). The first boot's release lands before
// the CPU ran anything useful, so resetting then changes nothing.
extern "C" volatile int ciclone_snes_in_reset, ciclone_snes_reset_edge;
// the cart's DAC, one SNES frame of it (44100 / 60.0988 Hz): pulled every frame, window or
// not, since the MCU refills the DAC buffer by the halves this consumes
static std::vector<int16_t> g_cart;
static void cart_frame(void) {
  static double acc = 0;
  acc += 44100.0 / 60.0988;
  int n = (int)acc;
  acc -= n;
  g_cart.assign((size_t)n * 2, 0);
  ciclone_model_lock();
  if (ciclone::active_model()) ciclone::active_model()->cart_samples(g_cart.data(), n);
  ciclone_model_unlock();
  // CICLONE_CART_PCM=<file>: the cart's DAC as it played, raw 44100 Hz 16-bit stereo (to check
  // what the MCU streamed without listening)
  static FILE *dump = nullptr; static bool dump_init = false;
  if (!dump_init) { dump_init = true; if (const char *f = getenv("CICLONE_CART_PCM")) dump = fopen(f, "wb"); }
  if (dump) { fwrite(g_cart.data(), 2, g_cart.size(), dump); fflush(dump); }
}
static void snes_frame(void) {
  if (ciclone_snes_reset_edge) { ciclone_snes_reset_edge = 0; snes_reset(); }
  if (!ciclone_snes_in_reset) {
    snes_run();
    if (ciclone::FpgaModel *m = ciclone::active_model()) m->snes_frame();
  }
  cart_frame();
}
static void paced_run(void) { snes_frame(); pace((double)g_frame + 1); }

// ---- hooks FORTES do chip sd2snes (sobrescrevem os weak do libsnes) ----
extern "C" {
  int ciclone_chip_active(void) { return ciclone::active_model() != nullptr; }
  uint8_t ciclone_chip_snes_read(uint32_t addr) {
    g_chip_reads++;
    // SEM o mutex do modelo: o menu roda da PSRAM, então isto é chamado milhões de vezes por
    // segundo e, com lock, a thread do SNES monopolizava o mutex e deixava a do MCU sem vez
    // (MCU "lento" -> o SNES atropelava os handshakes, coisa que não acontece no console).
    // No hardware a leitura é de memória dual-port; aqui é leitura de byte de um vetor que
    // nunca realoca -- a corrida com uma escrita do MCU é benigna. Escritas seguem travadas.
    pace_chip(addr);
    ciclone::FpgaModel *m = ciclone::active_model();
    return m ? m->snes_read(addr) : 0xff;
  }
  void ciclone_chip_snes_write(uint32_t addr, uint8_t data) {
    g_chip_writes++;
    pace_chip(addr);
    ciclone_model_lock();
    ciclone::FpgaModel *m = ciclone::active_model();
    if (m) m->snes_write(addr, data);
    ciclone_model_unlock();
  }
  // The rest of the cart edge (bsnes chip snoop hooks). All on the SNES thread and, like the
  // reads, without the model mutex: they touch only SNES-side model state and PSRAM shadows.
  void ciclone_chip_irq_vector(uint32_t vector, int native) {
    if (ciclone::FpgaModel *m = ciclone::active_model()) m->cpu_vector_fetch(vector, native);
  }
  void ciclone_chip_bus_snoop(uint32_t addr, uint8_t data, int write) {
    if (ciclone::FpgaModel *m = ciclone::active_model()) m->snoop(addr, data, write);
  }
  void ciclone_chip_reset(void) {
    if (ciclone::FpgaModel *m = ciclone::active_model()) m->snes_reset_strobe();
  }
  // CDC (transporte FxPakPro): stub no host_runner - USB desligado no M2. O servidor
  // FxPakPro REAL (usbinterface.c) está na libsd2snesfw, mas só é exercitado no M2.5
  // (via cdc_pty.c/teste). Aqui só satisfaz o link.
  uint32_t CDC_block_send(uint8_t *b, uint32_t n) { (void)b; return n; }
  void     CDC_block_init(uint8_t *b, uint32_t n) { (void)b; (void)n; }
}

static std::vector<uint8_t> read_file(const char *p) {
  FILE *f = fopen(p, "rb");
  if (!f) { fprintf(stderr, "nao abriu %s\n", p); exit(2); }
  fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
  std::vector<uint8_t> v((size_t)sz);
  if (fread(v.data(), 1, (size_t)sz, f) != (size_t)sz) { fprintf(stderr, "read fail\n"); exit(2); }
  fclose(f); return v;
}
static void write_ppm(const char *out, int frames) {
  if (g_w == 0) { fprintf(stderr, "nenhum frame\n"); exit(1); }
  FILE *o = fopen(out, "wb");
  fprintf(o, "P6\n%u %u\n255\n", g_w, g_h);
  fwrite(g_rgb.data(), 1, g_rgb.size(), o); fclose(o);
  fprintf(stderr, "ok: %ux%u -> %s (%d frames, chip reads=%ld writes=%ld)\n",
          g_w, g_h, out, frames, g_chip_reads, g_chip_writes);
}

static void *fw_thread(void *) { ciclone_fw_main(); return nullptr; }  // nunca retorna

// ---- entrada roteirizada (headless): --keys / --shots ----
// --keys  "F:BTN[+BTN...][:HOLD],..."  aperta BTN no quadro F por HOLD quadros (default 4).
//         BTN: B Y SEL START UP DOWN LEFT RIGHT A X L R, or MENU (the armed in-game menu combo).
// --shots "F:saida.ppm,..."            grava o quadro F (depois de emulado) em PPM.
struct KeyEv { int frame, hold; uint16_t mask; bool menu; };
struct ShotEv { int frame; std::string path; };
static std::vector<KeyEv> g_keys;
static std::vector<ShotEv> g_shots;
static int btn_id(const std::string &n) {
  static const char *names[12] = {"B","Y","SEL","START","UP","DOWN","LEFT","RIGHT","A","X","L","R"};
  for (int i = 0; i < 12; i++) if (n == names[i]) return i;
  fprintf(stderr, "botao desconhecido: %s\n", n.c_str()); exit(2);
}
static std::vector<std::string> split(const std::string &s, char d) {
  std::vector<std::string> v; size_t a = 0, b;
  while ((b = s.find(d, a)) != std::string::npos) { v.push_back(s.substr(a, b - a)); a = b + 1; }
  v.push_back(s.substr(a)); return v;
}
static void parse_keys(const char *arg) {
  for (auto &ev : split(arg, ',')) {
    if (ev.empty()) continue;
    auto f = split(ev, ':');
    KeyEv k{atoi(f[0].c_str()), f.size() > 2 ? atoi(f[2].c_str()) : 4, 0, false};
    for (auto &b : split(f.at(1), '+')) {
      if (b == "MENU") k.menu = true;
      else k.mask |= (uint16_t)(1u << btn_id(b));
    }
    if (k.menu && f.size() <= 2) k.hold = MENU_HOLD;
    g_keys.push_back(k);
  }
}
static void parse_shots(const char *arg) {
  for (auto &ev : split(arg, ',')) {
    if (ev.empty()) continue;
    size_t c = ev.find(':');
    g_shots.push_back({atoi(ev.substr(0, c).c_str()), ev.substr(c + 1)});
  }
}
// ---- modo --serve: protocolo de linhas no stdin/stdout p/ o harness de testes ----
// O stdout ORIGINAL vira o canal do protocolo; o stdout da libc (printf da firmware) vai
// para --fwlog (line-buffered, o harness lê ao vivo). Comandos (uma linha, resposta "ok ..."):
//   step N              roda N quadros com os botões atuais     -> ok <quadro>
//   buttons MASK        segura os botões (hex, bit = id libsnes) -> ok
//   menumask            o combo do menu in-game armado agora (a tecla M da janela) -> ok <hex>
//   peek SPACE ADDR LEN hex; SPACE = wram vram cgram oam aram psram snescmd -> ok <hex>
//   shot PATH           grava o último quadro em PPM             -> ok
//   quit
extern "C" uint8_t *ciclone_snes_memory(unsigned id, unsigned *size);
static FILE *g_proto = nullptr;

static void serve_loop(ciclone::FpgaModel *m) {
  char line[1024];
  g_speed = 4.0;
  if (const char *sp = getenv("CICLONE_SPEED")) g_speed = atof(sp);
  fprintf(g_proto, "ready\n"); fflush(g_proto);
  while (fgets(line, sizeof line, stdin)) {
    char cmd[32] = {0};
    if (sscanf(line, "%31s", cmd) != 1) continue;
    if (!strcmp(cmd, "step")) {
      long n = 1; sscanf(line + 4, "%ld", &n);
      for (long i = 0; i < n; i++) { paced_run(); g_frame++; }
      fprintf(g_proto, "ok %ld\n", g_frame);
    } else if (!strcmp(cmd, "menumask")) {
      fprintf(g_proto, "ok %x\n", menu_combo_mask());
    } else if (!strcmp(cmd, "buttons")) {
      unsigned mask = 0; sscanf(line + 7, "%x", &mask);
      for (int i = 0; i < 16; i++) g_buttons[i] = (mask >> i) & 1;
      fprintf(g_proto, "ok\n");
    } else if (!strcmp(cmd, "peek")) {
      char space[16] = {0}; unsigned addr = 0, len = 0;
      if (sscanf(line, "peek %15s %x %x", space, &addr, &len) != 3) { fprintf(g_proto, "err syntax\n"); fflush(g_proto); continue; }
      std::string out; out.reserve(len * 2);
      static const char hx[] = "0123456789abcdef";
      auto put = [&](uint8_t v) { out += hx[v >> 4]; out += hx[v & 15]; };
      int id = !strcmp(space, "wram") ? 0 : !strcmp(space, "vram") ? 1 : !strcmp(space, "cgram") ? 2
             : !strcmp(space, "oam") ? 3 : !strcmp(space, "aram") ? 4 : -1;
      if (id >= 0) {
        unsigned size = 0; uint8_t *p = ciclone_snes_memory((unsigned)id, &size);
        if (!p || !size) { fprintf(g_proto, "err nomem\n"); fflush(g_proto); continue; }
        for (unsigned i = 0; i < len; i++) put(p[(addr + i) % size]);
      } else if (!strcmp(space, "psram")) {
        ciclone_model_lock();
        const uint8_t *p = m->psram_ptr();
        for (unsigned i = 0; i < len; i++) put(p[(addr + i) & 0xFFFFFF]);
        ciclone_model_unlock();
      } else if (!strcmp(space, "snescmd")) {
        ciclone_model_lock();
        for (unsigned i = 0; i < len; i++) put(m->peek_snescmd((uint16_t)(addr + i)));
        ciclone_model_unlock();
      } else { fprintf(g_proto, "err space\n"); fflush(g_proto); continue; }
      fprintf(g_proto, "ok %s\n", out.c_str());
    } else if (!strcmp(cmd, "sfx")) {       // the SFX fetcher's last SFX_PLAY: base len
      uint32_t base = 0, len = 0;
      ciclone_model_lock(); m->sfx_state(&base, &len); ciclone_model_unlock();
      fprintf(g_proto, "ok %06x %06x\n", base, len); fflush(g_proto);
    } else if (!strcmp(cmd, "dac")) {       // the MSU-1 DAC buffer: playing, read and write pointers
      ciclone_model_lock(); int on = m->dac_playing(), loud = m->dac_loud(); ciclone_model_unlock();
      fprintf(g_proto, "ok %d %d\n", on, loud); fflush(g_proto);
    } else if (!strcmp(cmd, "shot")) {
      char path[900] = {0}; sscanf(line, "shot %899s", path);
      write_ppm(path, (int)g_frame);
      fprintf(g_proto, "ok\n");
    } else if (!strcmp(cmd, "quit")) {
      fprintf(g_proto, "ok\n"); fflush(g_proto); fflush(stdout); _exit(0);
    } else {
      fprintf(g_proto, "err unknown %s\n", cmd);
    }
    fflush(g_proto);
  }
  fflush(stdout);
  _exit(0);   // stdin fechou (harness morreu): a thread da firmware nunca retorna
}

// aplica o estado dos botões do quadro f e roda 1 quadro; depois grava o shot, se houver
static void run_scripted_frame(int f) {
  for (int i = 0; i < 16; i++) g_buttons[i] = 0;
  for (auto &k : g_keys)
    if (f >= k.frame && f < k.frame + k.hold) {
      uint16_t mask = k.mask | (k.menu ? menu_combo_mask() : 0);
      for (int i = 0; i < 16; i++) if (mask & (1u << i)) g_buttons[i] = 1;
    }
  snes_frame();
  for (auto &s : g_shots) if (s.frame == f) write_ppm(s.path.c_str(), f + 1);
}

// ---- janela interativa (SDL): mesmo core/chip/firmware, mas com tela + teclado ----
#ifdef CICLONE_SDL
#include <SDL.h>
static void run_gui(const char *title) {
  // The window runs at the console's own speed. With g_speed = 0 the only brake was
  // SDL's vsync, which is the DISPLAY's refresh (120 Hz on a ProMotion Mac, none at all
  // when vsync is refused): the menu's pad auto-repeat (16 frames, then every 3) fired
  // on a normal tap. CICLONE_SPEED still overrides (0 = as fast as it goes).
  g_speed = 1.0;
  if (const char *sp = getenv("CICLONE_SPEED")) g_speed = atof(sp);
  if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) { fprintf(stderr, "SDL init: %s\n", SDL_GetError()); return; }
  // the console's DSP runs at 32040 Hz, stereo 16-bit; SDL resamples to the device
  SDL_AudioSpec want = {}, have = {};
  want.freq = 32040; want.format = AUDIO_S16SYS; want.channels = 2; want.samples = 1024;
  SDL_AudioDeviceID adev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
  if (adev) { SDL_PauseAudioDevice(adev, 0); g_audio_on = true; }
  else fprintf(stderr, "SDL audio: %s (sem som)\n", SDL_GetError());
  const int scale = 3;
  SDL_Window *win = SDL_CreateWindow(title, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                                     256*scale, 224*scale, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
  if (!win) { fprintf(stderr, "SDL_CreateWindow falhou: %s\n", SDL_GetError()); SDL_Quit(); return; }
  SDL_RaiseWindow(win);                 // traz a janela pra frente (binário CLI, sem .app bundle)
  SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_PRESENTVSYNC);
  if (!ren) ren = SDL_CreateRenderer(win, -1, 0);   // fallback sem vsync
  if (!ren) { fprintf(stderr, "SDL_CreateRenderer falhou: %s\n", SDL_GetError()); SDL_DestroyWindow(win); SDL_Quit(); return; }
  SDL_Texture *tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_RGB24, SDL_TEXTUREACCESS_STREAMING, 512, 480);
  // teclado -> id de joypad do libsnes (0=B 1=Y 2=Sel 3=Start 4=Up 5=Dn 6=Lf 7=Rt 8=A 9=X 10=L 11=R)
  struct { SDL_Scancode sc; int id; } map[] = {
    {SDL_SCANCODE_UP,4},{SDL_SCANCODE_DOWN,5},{SDL_SCANCODE_LEFT,6},{SDL_SCANCODE_RIGHT,7},
    {SDL_SCANCODE_Z,0},{SDL_SCANCODE_X,8},{SDL_SCANCODE_A,1},{SDL_SCANCODE_S,9},
    {SDL_SCANCODE_RETURN,3},{SDL_SCANCODE_RSHIFT,2},{SDL_SCANCODE_LSHIFT,2},
    {SDL_SCANCODE_Q,10},{SDL_SCANCODE_W,11},
  };
  printf("Janela aberta. Setas=D-pad  Z=B X=A A=Y S=X  Enter=Start Shift=Select  Q=L W=R  M=menu in-game  ESC=sair\n");
  fflush(stdout);
  bool running = true;
  while (running) {
    SDL_Event ev;
    while (SDL_PollEvent(&ev)) {
      if (ev.type == SDL_QUIT) running = false;
      else if (ev.type == SDL_KEYDOWN && ev.key.keysym.scancode == SDL_SCANCODE_ESCAPE) running = false;
      else if (ev.type == SDL_KEYDOWN && ev.key.keysym.scancode == SDL_SCANCODE_M) {
        if (!ev.key.repeat) press_menu_combo();
      }
      else if (ev.type == SDL_KEYDOWN || ev.type == SDL_KEYUP) {
        int v = (ev.type == SDL_KEYDOWN) ? 1 : 0;
        for (auto &m : map) if (m.sc == ev.key.keysym.scancode) g_buttons[m.id] = v;
      }
    }
    snes_frame();  // 1 frame
    if (g_menu_hold > 0) g_menu_hold--;
    g_frame++;
    if (adev && !g_audio.empty()) {
      // the cart's DAC (44100 Hz, this frame's: cart_frame) mixed into the S-SMP's frame
      // (32040 Hz), nearest sample
      size_t n = g_audio.size() / 2, got = g_cart.size() / 2;
      for (size_t i = 0; got && i < n; i++) {
        size_t j = i * got / n;
        for (int c = 0; c < 2; c++) {
          int v = g_audio[2 * i + c] + g_cart[2 * j + c] * 3 / 4;
          g_audio[2 * i + c] = (int16_t)(v > 32767 ? 32767 : v < -32768 ? -32768 : v);
        }
      }
      // keep at most ~0.15 s queued: past that the emulation ran ahead (a hitch), drop
      if (SDL_GetQueuedAudioSize(adev) < 32040 * 4 * 15 / 100)
        SDL_QueueAudio(adev, g_audio.data(), (Uint32)(g_audio.size() * sizeof(int16_t)));
      g_audio.clear();
    }
    pace((double)g_frame);   // real time (CICLONE_SPEED): vsync alone is not a clock
    if (g_w && !g_rgb.empty()) {
      SDL_Rect r = {0,0,(int)g_w,(int)g_h};
      SDL_UpdateTexture(tex, &r, g_rgb.data(), (int)g_w*3);
      SDL_RenderClear(ren); SDL_RenderCopy(ren, tex, &r, NULL); SDL_RenderPresent(ren);
    }
  }
  if (adev) { g_audio_on = false; SDL_CloseAudioDevice(adev); }
  SDL_DestroyTexture(tex); SDL_DestroyRenderer(ren); SDL_DestroyWindow(win); SDL_Quit();
}
#else
static void run_gui(const char *title) { (void)title;
  fprintf(stderr, "recompile com -DCICLONE_SDL (use host_runner/build_gui.sh) p/ a janela\n"); }
#endif

int main(int argc, char **argv) {
  bool sd2snes = false, fw = false, gui = false, serve = false;
  const char *fwlog = nullptr;
  const char *rompath = nullptr, *outpath = "frame.ppm"; int frames = 300;
  int pos = 0;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--sd2snes")) sd2snes = true;
    else if (!strcmp(argv[i], "--fw")) { fw = true; sd2snes = true; }
    else if (!strcmp(argv[i], "--gui")) { gui = true; fw = true; sd2snes = true; }  // janela interativa
    else if (!strcmp(argv[i], "--serve")) { serve = true; fw = true; sd2snes = true; }  // harness de testes
    else if (!strcmp(argv[i], "--fwlog") && i + 1 < argc) fwlog = argv[++i];
    else if (!strcmp(argv[i], "--keys") && i + 1 < argc) parse_keys(argv[++i]);
    else if (!strcmp(argv[i], "--shots") && i + 1 < argc) parse_shots(argv[++i]);
    else if (pos == 0) { rompath = argv[i]; pos++; }
    else if (pos == 1) { outpath = argv[i]; pos++; }
    else if (pos == 2) { frames = atoi(argv[i]); pos++; }
  }
  if (!rompath) { fprintf(stderr, "uso: %s [--sd2snes|--fw] [--keys F:BTN[+BTN][:HOLD],...] [--shots F:out.ppm,...] <rom-ou-sdimg> [out.ppm] [frames]\n", argv[0]); return 2; }

  // ---- modo --fw: firmware REAL (libsd2snesfw) numa thread + SNES via chip ----
  if (fw) {
    ciclone::FpgaModel *m = ciclone::make_behavioral_model();
    ciclone::set_active_model(m);
    if (ciclone_sd_open(rompath) != 0) { fprintf(stderr, "nao abriu SD image %s\n", rompath); return 2; }
    // sincronia de comando em todo modo com a firmware real (janela, roteiro e --serve)
    g_sync = !(getenv("CICLONE_SYNC") && !strcmp(getenv("CICLONE_SYNC"), "0"));
    if (serve) {   // stdout original = protocolo; printf da firmware -> --fwlog (ou /dev/null)
      g_proto = fdopen(dup(1), "w");
      if (!freopen(fwlog ? fwlog : "/dev/null", "w", stdout)) { fprintf(stderr, "fwlog?\n"); return 2; }
      setvbuf(stdout, nullptr, _IOLBF, 0);
    }
    ciclone_set_uart_echo(0);
    pthread_t th; pthread_create(&th, nullptr, fw_thread, nullptr);
    // espera o firmware bootar: carregar o menu na PSRAM + sinalizar RDY ($55 em $2A02 -> snescmd[0x202])
    int waited = 0;
    while (waited < 8000 && m->peek_snescmd(0x2a02 & 0x3ff) != 0x55) { usleep(2000); waited += 2; }
    fprintf(stderr, "firmware boot: %s apos %dms (snescmd[$2A02]=0x%02x, mapper=%u)\n",
            (m->peek_snescmd(0x202) == 0x55) ? "RDY" : "TIMEOUT", waited, m->peek_snescmd(0x202), m->mapper());
    snes_init();
    snes_set_video_refresh(vr); snes_set_audio_sample(asample);
    snes_set_input_poll(ipoll); snes_set_input_state(istate);
    static const uint8_t dummy[1024] = {0};
    const char *manifest = "<cartridge><sd2snes/></cartridge>";
    if (!snes_load_cartridge_normal(manifest, dummy, sizeof(dummy))) { fprintf(stderr, "load falhou\n"); return 1; }
    if (serve) serve_loop(m);
    if (gui) { run_gui("Ciclone - sd2snes (firmware REAL + FpgaModel)"); }
    else { for (int i = 0; i < frames; i++) run_scripted_frame(i); write_ppm(outpath, frames); }
    fflush(stdout); fflush(stderr);  // printf do firmware vai p/ o stdout da libc: sem isso o _exit o perde
    _exit(0);  // firmware thread ainda gira no menu loop
  }

  std::vector<uint8_t> rom = read_file(rompath);

  snes_init();
  snes_set_video_refresh(vr);
  snes_set_audio_sample(asample);
  snes_set_input_poll(ipoll);
  snes_set_input_state(istate);

  if (sd2snes) {
    // instancia o FpgaModel e pré-carrega o ROM na PSRAM (simula o que o firmware faria)
    ciclone::FpgaModel *m = ciclone::make_behavioral_model();
    ciclone::set_active_model(m);
    memcpy(m->psram_ptr(), rom.data(), rom.size());
    // mapper 7 (menu) + rom_mask via o seam SPI (caminhos testados)
    ciclone_spi_select(); ciclone_spi_txrx(0x30 | 7); ciclone_spi_deselect();
    uint32_t mask = 1; while (mask < rom.size()) mask <<= 1; mask -= 1;
    ciclone_spi_select(); ciclone_spi_txrx(0x10);
    ciclone_spi_txrx((mask >> 16) & 0xff); ciclone_spi_txrx((mask >> 8) & 0xff); ciclone_spi_txrx(mask & 0xff);
    ciclone_spi_deselect();
    const char *manifest = "<cartridge><sd2snes/></cartridge>";
    if (!snes_load_cartridge_normal(manifest, rom.data(), (unsigned)rom.size())) { fprintf(stderr, "load falhou\n"); return 1; }
    fprintf(stderr, "modo sd2snes: chip ativo=%d, PSRAM pre-carregada (%zu bytes), mapper=7 mask=0x%x\n",
            ciclone_chip_active(), rom.size(), mask);
  } else {
    if (!snes_load_cartridge_normal(NULL, rom.data(), (unsigned)rom.size())) { fprintf(stderr, "load falhou\n"); return 1; }
  }

  for (int i = 0; i < frames; i++) snes_run();
  write_ppm(outpath, frames);
  return 0;
}
