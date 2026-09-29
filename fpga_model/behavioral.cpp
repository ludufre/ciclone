// Ciclone - FpgaModel comportamental (seam #2, backend A).
// Modela o que o firmware e o SNES observam do FPGA: PSRAM/SRAM/SNESCMD, o
// interpretador de comandos SPI do MCU e o decode de endereços do barramento SNES.
// Evolui a máquina de estados de tests/host/shim.c para o command set real.
//
// Princípio robusto: só os comandos do caminho boot+load são modelados com precisão;
// qualquer comando não modelado vira PH_SKIP (ignora bytes até o DESELECT). Como cada
// função do firmware faz SELECT...DESELECT em torno de UM comando, isso cobre o resto
// sem depender de contagens de byte exatas.
#include "fpga_model.h"
#include "../include/ciclone_seam.h"
#include <vector>
#include <algorithm>
#include <cstring>
#include <cstdint>
#include <mutex>
#include <ctime>
#include <cstdio>
#include <cstdlib>

// Mutex global do modelo: o firmware (thread MCU) e o SNES (thread do bsnes) tocam o
// MESMO FpgaModel. Lado MCU trava nas funcoes de seam abaixo; lado SNES trava via
// ciclone_model_lock/unlock (usado pelos hooks ciclone_chip_* do host_runner).
static std::mutex g_model_mtx;

// "MCU ocupado": leu um comando (MCU_CMD != 0) e ainda não voltou ao polling (ler MCU_CMD = 0).
// O runner segura os acessos do SNES à janela SNESCMD enquanto isso -- ver ciclone_mcu_busy().
#include <atomic>
static std::atomic<int> g_mcu_busy{0};

// CICLONE_TRACE_CMD=<arquivo>: registra, com timestamp, o tráfego do handshake MCU_CMD ($2A00)
// / SNES_CMD ($2A02) dos DOIS lados -- para diagnosticar raça de protocolo menu<->firmware.
static FILE *g_trace = nullptr;
static bool g_trace_init = false;
static void trace_cmd(const char *who, const char *op, unsigned idx, unsigned v) {
  if (!g_trace_init) {
    g_trace_init = true;
    if (const char *f = getenv("CICLONE_TRACE_CMD")) { g_trace = fopen(f, "w"); if (g_trace) setvbuf(g_trace, nullptr, _IOLBF, 0); }
  }
  if (!g_trace) return;
  struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
  static double t0 = 0; double t = ts.tv_sec + ts.tv_nsec * 1e-9; if (t0 == 0) t0 = t;
  fprintf(g_trace, "%10.3f ms  %-4s %-5s %s = $%02X\n", (t - t0) * 1e3, who, op, idx == 0x200 ? "MCU_CMD " : "SNES_CMD", v);
}

namespace ciclone {

static FpgaModel *g_active = nullptr;
void       set_active_model(FpgaModel *m) { g_active = m; }
FpgaModel *active_model() { return g_active; }

namespace {

constexpr uint32_t PSRAM_SIZE = 0x1000000, PSRAM_MASK = 0x0FFFFFF; // 16 MB
constexpr uint16_t SNESCMD_SIZE = 0x400;                           // 1 KB
constexpr uint16_t FEAT_CMD_UNLOCK = (1 << 5);
constexpr uint32_t MENU_BASE = 0xC00000;  // SRAM_MENU_ADDR (memory.h): menu vive aqui na PSRAM
constexpr uint32_t SAVERAM_BASE = 0xE00000;  // SRAM_SAVE_ADDR: the game's save RAM lives in PSRAM too

// cheat.v's global flag word (FPGA_CMD_CHEAT_WRITE index 7: low byte sets, high byte clears)
enum HookFlag : uint8_t { HK_CHEAT = 1, HK_NMI = 2, HK_IRQ = 4, HK_HOLDOFF = 8, HK_BUTTONS = 16,
                          HK_WRAM = 32, HK_SAVESTATE = 64 };
constexpr int HOLDOFF_FRAMES = 601;         // 960M clocks at 96 MHz = 10 s of SNES time
// ctx.v register shadows in PSRAM (what the in-game menu snapshots and restores on exit)
constexpr uint32_t CTX_PPUREG = 0xF90500;   // + 2*PA: word {previous write, latest}
constexpr uint32_t CTX_CPUREG = 0xF90700;   // + addr[8:0]: $4200-$420D, $43x0-$43xA
constexpr uint32_t CTX_MISC   = 0xF90420;   // + addr[0]: the pad the NMI stub stored at $2BF0/1

enum Phase {
  PH_CMD, PH_SKIP, PH_ADDR, PH_MASK, PH_RAMBASE,
  PH_WRITEMEM, PH_READMEM, PH_SCADDR, PH_SCREAD, PH_SCWRITE,
  PH_TEST, PH_STATUS, PH_SFX, PH_DACADDR, PH_DACPTR,
  PH_FEATURE, PH_CHEAT_IDX, PH_CHEAT,
};
enum MaskWhich { MW_ROM, MW_RAM };

class Behavioral : public FpgaModel {
public:
  Behavioral() {
    psram.assign(PSRAM_SIZE, 0x00);
    reset();
  }

  void reset() override {
    memset(snescmd, 0, sizeof(snescmd));
    cursor = 0; rom_mask = PSRAM_MASK; ram_mask = 0x7FFFF; ram_base = 0;
    map = 7; features = 0; status = 0;
    phase = PH_CMD; srtc_ptr = 15; srtc_latch = 0;
    hook_flags = 0; cheat_mask = 0;
    snescmd_unlock = unlock_disable = force_entry = vec_armed = false;
    vec_unlock = 0; locked_vec = 0xFFFFFF; return_vector = 0xEA; pad_data = 0; reset_unlock = 0;
    holdoff = 0; snes_ajr = pad_latch = false; pad_cnt = 0; map_unlock_bits = 0; rBG = rM7 = 0;
    nmi_usage = irq_usage = 0; auto_nmi = true; auto_irq = false;
  }

  // fpga_pgm: hardware reinicializa a BRAM SNESCMD na reconfig; PSRAM/SRAM externas ficam.
  void reconfigure(int core) override { (void)core; memset(snescmd, 0, sizeof(snescmd)); phase = PH_CMD; }

  // -------- lado MCU (SPI) --------
  void spi_select()   override { phase = PH_CMD; }
  void spi_deselect() override { phase = PH_CMD; }
  int  mcu_rdy()      override { return 1; }
  uint8_t spi_txrx(uint8_t tx) override { return spi_byte(tx); }

  void dma_write(const uint8_t *buf, uint32_t len) override {
    for (uint32_t i = 0; i < len; i++) { psram[cursor & PSRAM_MASK] = buf[i]; cursor = (cursor + 1) & PSRAM_MASK; }
  }

  // -------- lado SNES --------
  uint8_t snes_read(uint32_t a)  override { return decode(a, 0, 0); }
  void    snes_write(uint32_t a, uint8_t d) override { decode(a, 1, d); }
  void    cpu_vector_fetch(uint32_t vector, int native) override;
  void    snoop(uint32_t a, uint8_t d, int write) override;
  void    snes_reset_strobe() override;
  void    snes_frame() override;

  // -------- introspecção --------
  uint8_t *psram_ptr() override { return psram.data(); }

  int sfx_samples(int16_t *out, int frames) override {
    int k = 0;
    for (; k < frames && sfx_pos + 4 <= sfx_len; k++, sfx_pos += 4) {
      uint32_t p = sfx_base + sfx_pos;
      out[2 * k]     = (int16_t)(psram[p & PSRAM_MASK] | psram[(p + 1) & PSRAM_MASK] << 8);
      out[2 * k + 1] = (int16_t)(psram[(p + 2) & PSRAM_MASK] | psram[(p + 3) & PSRAM_MASK] << 8);
    }
    return k;
  }
  void sfx_state(uint32_t *base, uint32_t *len) override { *base = sfx_base; *len = sfx_len; }
  uint32_t sfx_base = 0, sfx_len = 0, sfx_pos = 0;

  // o DAC do MSU-1: buffer de 2 KB (512 quadros estéreo 16-bit), escrito pelo SD-DMA do MCU
  // no ponteiro de escrita (SETADDR|TGT_DACBUF) e lido a 44100 Hz enquanto toca (e1 pausa,
  // e2 toca, e3 posiciona a leitura). Metade lida = bit $4000 do status: o MCU reabastece
  // a metade que acabou de ser lida (msu1.c menu_sfx_pump). A leitura anda pelo RELÓGIO REAL,
  // como no console, e não por quadro do SNES: consumir um quadro de uma vez (735 amostras =
  // mais que o buffer inteiro) fazia o MCU nunca ver a troca de metade, e o buffer tocava em
  // loop. O que foi lido é copiado na hora para uma fila que o áudio da janela esvazia.
  uint8_t  dac_buf[2048] = {};
  uint16_t dac_wr = 0, dac_rd = 0;
  int      dac_on = 0;
  double   dac_t = 0, dac_frac = 0;
  std::vector<int16_t> dac_out;
  static double now_s() { struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts); return ts.tv_sec + ts.tv_nsec * 1e-9; }
  void dac_advance() {
    if (!dac_on) return;
    double t = now_s();
    dac_frac += (t - dac_t) * 44100.0;
    dac_t = t;
    int n = (int)dac_frac;
    if (n <= 0) return;
    dac_frac -= n;
    if (n > 4410) n = 4410;                        // a stall (debugger, host hiccup): drop it
    for (int k = 0; k < n; k++) {
      for (int c = 0; c < 2; c++) dac_out.push_back((int16_t)(dac_buf[dac_rd + 2 * c] | dac_buf[dac_rd + 2 * c + 1] << 8));
      dac_rd = (dac_rd + 4) & 2047;
    }
    static FILE *dump = nullptr; static bool dump_init = false;   // CICLONE_DAC_PCM=<file>: what the DAC read
    if (!dump_init) { dump_init = true; if (const char *f = getenv("CICLONE_DAC_PCM")) dump = fopen(f, "wb"); }
    if (dump) { fwrite(dac_out.data() + dac_out.size() - 2 * n, 2, 2 * n, dump); fflush(dump); }
    if (dac_out.size() > 2 * 8820) dac_out.erase(dac_out.begin(), dac_out.end() - 2 * 8820);  // nobody listening
  }
  void dac_write(const uint8_t *buf, uint32_t len) override {
    dac_advance();
    for (uint32_t i = 0; i < len; i++) { dac_buf[dac_wr] = buf[i]; dac_wr = (dac_wr + 1) & 2047; }
  }
  int dac_playing() override { return dac_on; }
  int dac_loud() override { int n = 0; for (uint8_t b : dac_buf) n += b != 0; return n; }
  int cart_samples(int16_t *out, int frames) override {
    int got = sfx_samples(out, frames);
    for (int k = got; k < frames; k++) out[2 * k] = out[2 * k + 1] = 0;
    dac_advance();
    int m = (int)std::min<size_t>((size_t)frames, dac_out.size() / 2);
    for (int k = 0; k < m; k++)
      for (int c = 0; c < 2; c++) {
        int v = out[2 * k + c] + dac_out[2 * k + c];
        out[2 * k + c] = (int16_t)(v > 32767 ? 32767 : v < -32768 ? -32768 : v);
      }
    dac_out.erase(dac_out.begin(), dac_out.begin() + 2 * m);
    return std::max(got, m);
  }
  uint8_t  peek_snescmd(uint16_t off) override { return snescmd[off & (SNESCMD_SIZE - 1)]; }
  uint8_t  mapper() override { return map; }

private:
  std::vector<uint8_t> psram;
  uint8_t  snescmd[SNESCMD_SIZE];
  uint32_t cursor, rom_mask, ram_mask;
  uint8_t  ram_base, map;
  uint16_t features, status;

  // ---- in-game hook (cheat.v). The MCU sets the flags and ROM cheats over SPI; everything
  // else is SNES-thread state (the read path takes no lock, see runner.cpp), hence the atomic.
  std::atomic<uint8_t> hook_flags{0};
  uint32_t cheat_addr[6] = {};
  uint8_t  cheat_data[6] = {}, cheat_mask;
  bool     snescmd_unlock, unlock_disable, force_entry;
  bool     vec_armed;          // the CPU pushed its state and is about to fetch a hooked vector
  uint8_t  vec_unlock;         // bytes of the hijacked vector still to serve (bit0 low, bit1 high)
  uint32_t locked_vec;         // the vector the hook came in through; jmp ($FFxx) to it = exit
  uint8_t  return_vector;      // its low byte, served at $2A6C for the stub's final jmp
  uint16_t pad_data;           // the pad the stub stores at $2BF0/1
  int      reset_unlock;       // reset vector fetches left to redirect to the reset hook $2A7D
  int      holdoff;            // frames left with hooks off (after reset, or the $85 gesture)
  bool     snes_ajr, pad_latch; int pad_cnt;   // main.v: $4200 bit0 / manual $4016 polling
  uint8_t  map_unlock_bits;    // $2BB2: Fx_rd Fx_wr Ex_rd Ex_wr snescmd_rd snescmd_wr (bit5..0)
  uint8_t  rBG, rM7;           // ctx.v: previous write of the double-write PPU registers
  int      nmi_usage, irq_usage; bool auto_nmi, auto_irq;   // NMI/IRQ hook autoselect
  uint8_t  d3_idx;             // FPGA_CMD_CHEAT_WRITE: index byte

  bool cmd_unlocked() const { return map == 7 || (features & FEAT_CMD_UNLOCK); }
  bool hook_enable() const { return holdoff == 0; }
  uint8_t nmicmd() const {
    switch (pad_data) {
      case 0x3030: return 0x80; case 0x2070: return 0x81; case 0x10b0: return 0x82;
      case 0x9030: return 0x83; case 0x5030: return 0x84; case 0x1070: return 0x85;
    }
    return 0;
  }
  // cheat.v's branch targets patched into the stub's `bra` operands while it runs
  uint8_t branch1() const {
    uint8_t f = hook_flags; bool wram = (f & HK_CHEAT) && (f & HK_WRAM), ss = f & HK_SAVESTATE;
    if (f & HK_BUTTONS) {
      if (snes_ajr) {
        if (nmicmd()) return 0x30;                          // nmi_echocmd
        if (wram) return 0x3a;                              // nmi_patches
        return (ss && (force_entry || pad_data)) ? 0x3f : 0x43;   // nmi_savestate / nmi_exit
      }
      if (pad_latch) return wram ? 0x3a : 0x43;             // game mid manual poll: hands off
      return 0x00;                                          // no AJR: the stub reads $4016
    }
    if (wram) return 0x3a;
    return (ss && pad_data) ? 0x3f : 0x43;
  }
  uint8_t branch2() const {
    uint8_t f = hook_flags;
    if (nmicmd() == 0x81) return 0x14;                      // nmi_stop
    if ((f & HK_CHEAT) && (f & HK_WRAM)) return 0x00;
    return (f & HK_SAVESTATE) ? 0x05 : 0x09;
  }
  uint8_t branch3() const { return (hook_flags & HK_SAVESTATE) ? 0x00 : 0x04; }
  // what cheat.v drives on a read, or -1 for "not this module"
  int hook_read(uint32_t a);
  void hook_write(uint32_t a, uint8_t d);

  // estado do interpretador SPI
  int      phase;
  int      cnt;            // bytes restantes de um campo multi-byte
  uint32_t acc;           // acumulador de campo
  int      mask_which;
  int      mem_autoinc;
  uint16_t snescmd_addr;
  int      sc_idx;        // índice de byte do setaddr do snescmd (lo,hi)
  int      sc_wr_first;   // 1 = próximo byte do d2 é o dado
  int      status_idx;    // 2->hi, 1->lo

  // S-RTC ($2800 dados / $2801 controle; srtc.v). O menu escreve $0D em $2801 e lê 13
  // nibbles de $2800: o 1º devolve $0F e trava o relógio, depois s1 s10 m1 m10 h1 h10
  // d1 d10 mês ano1 ano10 século. O relógio é o do host (o mesmo que o rtc_host.c dá ao
  // firmware), então FPGA_CMD_RTCSET ($E5) só é consumido.
  int      srtc_ptr;
  uint64_t srtc_latch;

  static uint64_t host_srtc_now() {
    time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
    // CICLONE_FIXED_TIME="YYYY-MM-DD HH:MM:SS": relógio congelado (testes determinísticos)
    if (const char *f = getenv("CICLONE_FIXED_TIME")) {
      struct tm ft = {};
      if (sscanf(f, "%d-%d-%d %d:%d:%d", &ft.tm_year, &ft.tm_mon, &ft.tm_mday,
                 &ft.tm_hour, &ft.tm_min, &ft.tm_sec) == 6) {
        ft.tm_year -= 1900; ft.tm_mon -= 1; ft.tm_isdst = -1;
        time_t t = mktime(&ft); localtime_r(&t, &lt);
      }
    }
    int y = lt.tm_year + 1900;
    auto d = [](int v, int n) { for (int i = 0; i < n; i++) v /= 10; return (uint64_t)(v % 10); };
    return d(lt.tm_sec,0) | d(lt.tm_sec,1) << 4 | d(lt.tm_min,0) << 8 | d(lt.tm_min,1) << 12
         | d(lt.tm_hour,0) << 16 | d(lt.tm_hour,1) << 20 | d(lt.tm_mday,0) << 24 | d(lt.tm_mday,1) << 28
         | d(lt.tm_mon+1,0) << 32 | d(lt.tm_mon+1,1) << 36 | d(y,0) << 40 | d(y,1) << 44
         | d(y,2) << 48 | d(y,3) << 52 | (uint64_t)lt.tm_wday << 56;
  }
  uint8_t srtc_read() {
    uint64_t r = srtc_latch; uint8_t v;
    auto nib = [&](int b) { return (uint8_t)((r >> b) & 0xf); };
    switch (srtc_ptr) {
      case 8:  v = nib(32) + nib(36) * 10; break;             // mês
      case 11: v = nib(48) + nib(52) * 10 - 10; break;         // século (20 -> 10)
      case 12: v = nib(56); break;                             // dia da semana
      case 15: srtc_latch = host_srtc_now(); v = 0x0f; break;
      case 9:  v = nib(40); break;                             // ano (unidade) -- o mês
      case 10: v = nib(44); break;                             // ocupou 8 bits, daí o +4
      default: v = (srtc_ptr < 8) ? nib(srtc_ptr * 4) : 0x0f;
    }
    srtc_ptr = (srtc_ptr == 13) ? 15 : ((srtc_ptr + 1) & 15);   // ponteiro de 4 bits: 15 -> 0
    return v;
  }

  uint8_t spi_byte(uint8_t tx) {
    switch (phase) {
      case PH_CMD: {
        uint8_t hi = tx & 0xf0;
        if      (tx == 0x00) { phase = PH_ADDR; cnt = 3; acc = 0; }                 // SETADDR mem
        else if (tx == 0x01) { phase = PH_DACADDR; cnt = 2; acc = 0; }              // SETADDR dac_buf
        else if (tx == 0xe1) { dac_advance(); dac_on = 0; phase = PH_SKIP; }        // DACPAUSE
        else if (tx == 0xe2) { if (!dac_on) { dac_on = 1; dac_t = now_s(); dac_frac = 0; } phase = PH_SKIP; } // DACPLAY
        else if (tx == 0xe3) { phase = PH_DACPTR; cnt = 2; acc = 0; }               // DACSETPTR
        else if (tx == 0x10) { phase = PH_MASK; cnt = 3; acc = 0; mask_which = MW_ROM; }
        else if (tx == 0x20) { phase = PH_MASK; cnt = 3; acc = 0; mask_which = MW_RAM; }
        else if (tx == 0x21) { phase = PH_RAMBASE; }
        else if (hi == 0x30) { map = tx & 0x0f; phase = PH_SKIP; }                  // SETMAPPER
        else if (hi == 0x40) { status &= ~0x8000; phase = PH_SKIP; }                // SDDMA (dados via disk_read)
        else if (hi == 0x80) { phase = PH_READMEM;  mem_autoinc = tx & 0x08; }      // READMEM
        else if (hi == 0x90) { phase = PH_WRITEMEM; mem_autoinc = tx & 0x08; }      // WRITEMEM
        else if (tx == 0xd0) { phase = PH_SCADDR; cnt = 2; acc = 0; sc_idx = 0; }   // SNESCMD setaddr
        else if (tx == 0xd1) { phase = PH_SCREAD; }                                 // SNESCMD read
        else if (tx == 0xd2) { phase = PH_SCWRITE; sc_wr_first = 1; }               // SNESCMD write
        else if (tx == 0xf0) { phase = PH_TEST; }                                   // TEST
        else if (tx == 0xf1) { dac_advance(); phase = PH_STATUS; status_idx = 2; }  // GETSTATUS
        else if (tx == 0xfb) { phase = PH_SFX; cnt = 6; acc = 0; }                  // SFX_PLAY base+len
        else if (tx == 0xfc) { sfx_pos = sfx_len; phase = PH_SKIP; }                // SFX_DISABLE: abort the fetcher
        else if (tx == 0xed) { phase = PH_FEATURE; cnt = 2; acc = 0; }              // SETFEATURE (MSB first)
        else if (tx == 0xd3) { phase = PH_CHEAT_IDX; }                              // CHEAT_WRITE idx + 32 bits
        else                 { phase = PH_SKIP; }
        return 0;
      }
      case PH_ADDR:
        acc = (acc << 8) | tx; if (--cnt == 0) { cursor = acc & PSRAM_MASK; phase = PH_SKIP; } return 0;
      case PH_MASK:
        acc = (acc << 8) | tx;
        if (--cnt == 0) { if (mask_which == MW_ROM) rom_mask = acc; else ram_mask = acc; phase = PH_SKIP; }
        return 0;
      case PH_RAMBASE: ram_base = tx; phase = PH_SKIP; return 0;
      case PH_WRITEMEM:
        psram[cursor & PSRAM_MASK] = tx; if (mem_autoinc) cursor = (cursor + 1) & PSRAM_MASK; return 0;
      case PH_READMEM: {
        uint8_t v = psram[cursor & PSRAM_MASK]; if (mem_autoinc) cursor = (cursor + 1) & PSRAM_MASK; return v;
      }
      case PH_SCADDR:  // d0: byte0=lo, byte1=hi
        acc |= (uint32_t)tx << (8 * sc_idx); sc_idx++;
        if (--cnt == 0) { snescmd_addr = acc & (SNESCMD_SIZE - 1); phase = PH_SKIP; } return 0;
      case PH_SCREAD: {
        uint8_t v = snescmd[snescmd_addr & (SNESCMD_SIZE - 1)];
        { unsigned ix = snescmd_addr & (SNESCMD_SIZE - 1); static uint8_t last_rd = 0xff;
          if (ix == 0x200) g_mcu_busy.store(v != 0);
          if (ix == 0x200 && v != last_rd) { trace_cmd("MCU", "read", ix, v); last_rd = v; } }
        snescmd_addr = (snescmd_addr + 1) & (SNESCMD_SIZE - 1); return v;
      }
      case PH_SCWRITE:
        if (sc_wr_first) { { unsigned ix = snescmd_addr & (SNESCMD_SIZE - 1);
                             if (ix == 0x200 || ix == 0x202) trace_cmd("MCU", "write", ix, tx); }
                           snescmd[snescmd_addr & (SNESCMD_SIZE - 1)] = tx;
                           snescmd_addr = (snescmd_addr + 1) & (SNESCMD_SIZE - 1); sc_wr_first = 0; }
        return 0;  // 2º byte (dummy) ignorado
      case PH_SFX:   // base[23:0] then len[23:0]; the last byte kicks it (newest wins)
        acc = (acc << 8) | tx;
        if (--cnt == 3) { sfx_base = acc & PSRAM_MASK; acc = 0; }
        else if (cnt == 0) {
          sfx_len = acc & 0xFFFFFF; sfx_pos = 0; phase = PH_SKIP;
          // sfxdma.v writes the effect into dac_buf and pads it with silence: whatever the
          // MCU streamed there before (a music clip cut short) is gone, not looped
          memset(dac_buf, 0, sizeof(dac_buf));
        }
        return 0;
      case PH_DACADDR:
        acc = (acc << 8) | tx; if (--cnt == 0) { dac_wr = acc & 2047; phase = PH_SKIP; } return 0;
      case PH_DACPTR:
        acc = (acc << 8) | tx; if (--cnt == 0) { dac_advance(); dac_rd = acc & 2047; phase = PH_SKIP; } return 0;
      case PH_FEATURE:
        acc = (acc << 8) | tx; if (--cnt == 0) { features = acc & 0xffff; phase = PH_SKIP; } return 0;
      case PH_CHEAT_IDX: d3_idx = tx & 7; phase = PH_CHEAT; cnt = 4; acc = 0; return 0;
      case PH_CHEAT:
        acc = (acc << 8) | tx;
        if (--cnt == 0) {                    // cheat.v pgm_we: 0-5 ROM cheats, 6 their enable mask, 7 flags
          if (d3_idx < 6) { cheat_addr[d3_idx] = acc >> 8; cheat_data[d3_idx] = acc & 0xff; }
          else if (d3_idx == 6) cheat_mask = acc & 0x3f;
          else hook_flags = (uint8_t)((hook_flags & ~((acc >> 8) & 0x7f)) | (acc & 0x7f));
          phase = PH_SKIP;
        }
        return 0;
      case PH_TEST: return 0xa5;
      case PH_STATUS: { uint16_t st = (status & ~0x4000) | (dac_rd >= 1024 ? 0x4000 : 0);
                        uint8_t v = (status_idx == 2) ? (st >> 8) : (st & 0xff);
                        if (--status_idx == 0) phase = PH_SKIP; return v; }
      case PH_SKIP: default: return 0;
    }
  }

  // SNESCMD BRAM: $2A00-$2DFF in banks $00-$3F/$80-$BF (address.v snescmd_enable), idx = addr&0x3FF.
  static bool snescmd_window(uint32_t a) {
    return ((a & 0x400000u) == 0) && ((a & 0xF800u) == 0x2800u) && (((a >> 9) & 3) == 1 || ((a >> 9) & 3) == 2);
  }

  // decode unificado: rw=0 read (retorna byte), rw=1 write (usa d). Espelha address.v + o mux de
  // dados do main.v: cheat.v (hooks, ROM cheats) > SNESCMD > IS_PATCH (identity) > mapper.
  uint8_t decode(uint32_t a, int rw, uint8_t d) {
    a &= 0xFFFFFF;
    if (!rw) { int h = hook_read(a); if (h >= 0) return (uint8_t)h; }
    else hook_write(a, d);
    if (snescmd_window(a)) {
      bool open = cmd_unlocked() || snescmd_unlock || (map_unlock_bits & (rw ? 1 : 2));
      if (open) {
        uint16_t i = a & (SNESCMD_SIZE - 1);
        if (rw && (i == 0x200 || i == 0x202)) trace_cmd("SNES", "write", i, d);   // $2A00/$2A02
        if (rw) { snescmd[i] = d; return 0; }
        return snescmd[i];
      }
    }
    uint8_t bank = (a >> 16) & 0xff;
    uint16_t off = a & 0xffff;
    if (map == 7 && !(bank & 0x40) && (off & 0xfffe) == 0x2800) {   // S-RTC do menu
      if (off == 0x2800) return rw ? 0 : srtc_read();
      if (rw && (d & 0x0f) == 0x0d) srtc_ptr = 15;                   // $2801: modo leitura
      return 0;
    }
    // IS_PATCH: the linear PSRAM window -- $C0-$FF while the hook holds snescmd_unlock (the
    // savestate handler and the in-game menu run from the menu's bank $C0), or $Ex/$Fx when
    // $2BB2 opens them. Readable and writable (IS_WRITABLE).
    uint8_t mu = map_unlock_bits;
    bool patch = (snescmd_unlock && bank >= 0xC0)
              || ((bank & 0xF0) == 0xF0 && (mu & (rw ? 0x10 : 0x20)))
              || ((bank & 0xF0) == 0xE0 && (mu & (rw ? 0x04 : 0x08)));
    uint32_t pa;
    bool writable = patch;
    if (patch) pa = a;
    else if (map == 7) {
      // Menu mapper: ROM = ({A[22:0]} & ROM_MASK) + $C00000; banks $F0-$FF are its "SRAM",
      // identity-mapped (CFG $FF0100, status $FF1000...).
      if ((bank & 0xF0) == 0xF0) { pa = a; writable = true; }
      else pa = ((a & 0x7FFFFF) & rom_mask) + MENU_BASE;
    } else {
      // The game's save RAM lives in PSRAM at SAVERAM_ADDR = $E00000 | base<<11 (the firmware
      // loads/saves the .srm there); a zero mask means no save RAM (SAVERAM_MASK[0] gate).
      uint32_t sbase = SAVERAM_BASE | ((uint32_t)ram_base << 11);
      bool has_sram = ram_mask & 1;
      if (map == 1) {                            // LoROM: SRAM @ $70-$7D/$F0-$FF (A15 low when ROM >= 32 Mbit)
        bool romsel = (bank & 0x7e) != 0x7e;     // $7E/$7F are WRAM
        if (has_sram && (bank & 0x70) == 0x70 && romsel && (!(off & 0x8000) || !(rom_mask & 0x200000))) {
          pa = sbase + ((((uint32_t)(bank & 0x1f) << 15) | (off & 0x7fff)) & ram_mask); writable = true;
        } else
          pa = ((((uint32_t)(~bank >> 7) & 1) << 22) | ((uint32_t)(bank & 0x7f) << 15) | (off & 0x7fff)) & rom_mask;
      } else {                                   // HiROM(0) / ExHiROM(2): SRAM @ $20-$3F/$A0-$BF:6000-7FFF
        if (has_sram && (bank & 0x60) == 0x20 && (off & 0xe000) == 0x6000) {
          pa = sbase + ((((uint32_t)(bank & 0x1f) << 13) | (off & 0x1fff)) & ram_mask); writable = true;
        } else if (map == 2)
          pa = ((((uint32_t)(~bank >> 7) & 1) << 22) | (a & 0x3FFFFF)) & rom_mask;
        else
          pa = (a & 0x7FFFFF) & rom_mask;
      }
    }
    pa &= PSRAM_MASK;
    // ROM_WE only on IS_WRITABLE (main.v:1334, address.v:220): save RAM, the menu's $F0-$FF
    // and the patch window. A game writing to its ROM space must not reach PSRAM.
    if (rw) { if (writable) psram[pa] = d; return 0; }
    return psram[pa];
  }
};

// ---------------------------------------------------------------- cheat.v, SNES side
// The CPU pushed PB/PC/P (native mode: 4 pushes) and will fetch `vector` next. cheat.v arms
// the hijack from the push pattern; bsnes tells us directly. Any other read disarms it.
void Behavioral::cpu_vector_fetch(uint32_t vector, int native) {
  if (vector == 0xffea) nmi_usage++;
  else if (vector == 0xffee) irq_usage++;
  uint8_t f = hook_flags;
  vec_armed = native && hook_enable()
           && ((vector == 0xffea && auto_nmi && (f & HK_NMI)) || (vector == 0xffee && auto_irq && (f & HK_IRQ)));
}

int Behavioral::hook_read(uint32_t a) {
  bool drive = !cmd_unlocked();          // main.v: cheat_hit & ~feat_cmd_unlock
  // Hook exit: after the stub wrote $2BFD, the CPU re-reading the vector it came in through
  // (its final jmp ($FFxx)) unmaps SNESCMD and the $C0-$FF window; that read gets the ROM.
  if (unlock_disable && (a >> 1) == (locked_vec >> 1)) {
    snescmd_unlock = unlock_disable = force_entry = false;
    return -1;
  }
  // Reset hook: the first reset vector fetch after /RESET goes to $2A7D (nmihook.a65 resethook)
  if (reset_unlock && (a == 0x00fffc || a == 0x00fffd)) {
    if (a == 0x00fffc) { snescmd_unlock = true; locked_vec = 0x00fffc; }
    reset_unlock--;
    if (drive) return a == 0x00fffc ? 0x7d : 0x2a;
    return -1;
  }
  // GAME -> INGAME HOOK: the armed first vector byte unlocks SNESCMD and serves $2A10
  if (vec_armed && (a == 0x00ffea || a == 0x00ffee)) {
    vec_armed = false;
    vec_unlock = 3; locked_vec = a; return_vector = a & 0xff; snescmd_unlock = true;
  }
  vec_armed = false;
  if (vec_unlock && (a >> 1) == (locked_vec >> 1)) {
    vec_unlock &= ~(1 << (a & 1));
    if (drive) return (a & 1) ? 0x2a : 0x10;
    return -1;
  }
  // the stub's patched operands (address.v: exact bank-$00 addresses)
  if (snescmd_unlock && hook_enable()) {
    int v = -1;
    switch (a) {
      case 0x002A1F: v = branch1();
                     if ((hook_flags & HK_SAVESTATE) && pad_data) force_entry = true;   // sticky entry
                     break;
      case 0x002A59: v = branch2(); break;
      case 0x002A5E: v = branch3(); break;
      case 0x002A6C: v = return_vector; break;
      case 0x002BF2: v = nmicmd(); break;
    }
    if (v >= 0 && drive) return v;
  }
  // ROM cheats (never while the hook runs: the $C0 overlay would get patched)
  if (cheat_mask && (hook_flags & HK_CHEAT) && !snescmd_unlock && drive)
    for (int i = 0; i < 6; i++)
      if ((cheat_mask >> i & 1) && cheat_addr[i] == a) return cheat_data[i];
  return -1;
}

void Behavioral::hook_write(uint32_t a, uint8_t d) {
  if (!snescmd_window(a)) return;
  uint16_t i = a & 0x3FF;                     // BRAM index: $2A00 -> $200, $2BFD -> $3FD
  if (i == 0x3f0) pad_data = (pad_data & 0xff00) | d;          // $2BF0/1: any write latches the pad
  else if (i == 0x3f1) pad_data = (pad_data & 0x00ff) | d << 8;
  if ((a & 0xFFFF) == 0x2BB2 && (snescmd_unlock || cmd_unlocked() || (map_unlock_bits & 1)))
    map_unlock_bits = d & 0x3f;
  if (!snescmd_unlock) return;
  if (i == 0x200) {                           // MCU_CMD written from inside the hook
    switch (d) {
      case 0x82: hook_flags |= HK_CHEAT; break;
      case 0x83: hook_flags &= (uint8_t)~HK_CHEAT; break;
      case 0x84: hook_flags &= (uint8_t)~(HK_NMI | HK_IRQ); break;
      case 0x85: holdoff = HOLDOFF_FRAMES; break;
    }
  } else if (i == 0x3fd) unlock_disable = true;   // NMI_VECT_DISABLE: arm the exit
}

// ---------------------------------------------------------------- the rest of the cart edge
void Behavioral::snoop(uint32_t a, uint8_t d, int write) {
  a &= 0xFFFFFF;
  if (a & 0x400000) return;                   // system area only ($00-$3F/$80-$BF)
  uint16_t off = a & 0xFFFF;
  if (!write) {                               // $4016 read: 16 reads end a manual poll
    if ((pad_cnt & 15) == 15) pad_latch = false;
    pad_cnt++;
    return;
  }
  if ((off & 0xFF00) == 0x2100) {             // ctx.v PPU register shadow, word per PA
    uint8_t pa = off & 0xff;
    bool bg = pa >= 0x0d && pa <= 0x14, m7 = (pa >= 0x0d && pa <= 0x0e) || (pa >= 0x1b && pa <= 0x20);
    bool keep = (pa <= 0x33 && pa != 0x04 && pa != 0x18 && pa != 0x19 && pa != 0x22) || (pa >= 0x81 && pa <= 0x83);
    if (keep) {
      psram[CTX_PPUREG + 2 * pa] = bg ? rBG : m7 ? rM7 : d;   // earlier byte of a double write
      psram[CTX_PPUREG + 2 * pa + 1] = d;
    }
    if (bg) rBG = d;
    if (m7) rM7 = d;
    return;
  }
  if (off == 0x4016) { pad_latch = true; pad_cnt = 0; }
  if (off == 0x4200) snes_ajr = d & 1;
  if ((off >= 0x4200 && off <= 0x420d) || ((off & 0xff80) == 0x4300 && (off & 0xf) <= 0xa))
    psram[CTX_CPUREG + (off & 0x1ff)] = d;
  if ((a & 0xFFFFFE) == 0x002BF0) psram[CTX_MISC + (a & 1)] = d;
}

void Behavioral::snes_reset_strobe() {
  snescmd_unlock = unlock_disable = vec_armed = false;
  vec_unlock = 0; locked_vec = 0xFFFFFF; reset_unlock = 2;
  if (hook_flags & HK_HOLDOFF) holdoff = HOLDOFF_FRAMES;
}

// ~one cheat.v usage window (2^21 clocks = 21.8 ms): pick the NMI hook if the game takes NMIs
// (or nothing at all), the IRQ hook for an IRQ-only frame loop. Not clocked inside the hook.
void Behavioral::snes_frame() {
  if (holdoff) holdoff--;
  if (snescmd_unlock) return;
  if (nmi_usage || !irq_usage) { auto_nmi = true; auto_irq = false; }
  else { auto_nmi = false; auto_irq = true; }
  nmi_usage = irq_usage = 0;
}

} // namespace

FpgaModel *make_behavioral_model() { return new Behavioral(); }

} // namespace ciclone

// -------- seam C (chamado pelo firmware via shims de HAL) --------
extern "C" {
int  ciclone_mcu_busy(void)     { return g_mcu_busy.load(); }
void ciclone_model_lock(void)   { g_model_mtx.lock(); }
void ciclone_model_unlock(void) { g_model_mtx.unlock(); }

void ciclone_spi_select(void)   { std::lock_guard<std::mutex> lk(g_model_mtx); if (ciclone::active_model()) ciclone::active_model()->spi_select(); }
void ciclone_spi_deselect(void) { std::lock_guard<std::mutex> lk(g_model_mtx); if (ciclone::active_model()) ciclone::active_model()->spi_deselect(); }
uint8_t ciclone_spi_txrx(uint8_t tx) { std::lock_guard<std::mutex> lk(g_model_mtx); return ciclone::active_model() ? ciclone::active_model()->spi_txrx(tx) : 0; }
int  ciclone_spi_mcu_rdy(void)  { std::lock_guard<std::mutex> lk(g_model_mtx); return ciclone::active_model() ? ciclone::active_model()->mcu_rdy() : 1; }
void ciclone_fpga_dma_write(const uint8_t *buf, uint32_t len) {
  std::lock_guard<std::mutex> lk(g_model_mtx);
  if (ciclone::active_model()) ciclone::active_model()->dma_write(buf, len);
}
void ciclone_fpga_dac_write(const uint8_t *buf, uint32_t len) {
  std::lock_guard<std::mutex> lk(g_model_mtx);
  if (ciclone::active_model()) ciclone::active_model()->dac_write(buf, len);
}
}
