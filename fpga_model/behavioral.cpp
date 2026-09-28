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
constexpr uint32_t SRAM_SIZE  = 0x0080000, SRAM_MASK  = 0x007FFFF; // 512 KB
constexpr uint16_t SNESCMD_SIZE = 0x400;                           // 1 KB
constexpr uint16_t FEAT_CMD_UNLOCK = (1 << 5);
constexpr uint32_t MENU_BASE = 0xC00000;  // SRAM_MENU_ADDR (memory.h): menu vive aqui na PSRAM

enum Phase {
  PH_CMD, PH_SKIP, PH_ADDR, PH_MASK, PH_RAMBASE,
  PH_WRITEMEM, PH_READMEM, PH_SCADDR, PH_SCREAD, PH_SCWRITE,
  PH_TEST, PH_STATUS,
};
enum MaskWhich { MW_ROM, MW_RAM };

class Behavioral : public FpgaModel {
public:
  Behavioral() {
    psram.assign(PSRAM_SIZE, 0x00);
    sram.assign(SRAM_SIZE, 0x00);
    reset();
  }

  void reset() override {
    memset(snescmd, 0, sizeof(snescmd));
    cursor = 0; rom_mask = PSRAM_MASK; ram_mask = SRAM_MASK; ram_base = 0;
    map = 7; features = 0; status = 0;
    phase = PH_CMD; srtc_ptr = 15; srtc_latch = 0;
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

  // -------- introspecção --------
  uint8_t *psram_ptr() override { return psram.data(); }
  uint8_t  peek_snescmd(uint16_t off) override { return snescmd[off & (SNESCMD_SIZE - 1)]; }
  uint8_t  mapper() override { return map; }

private:
  std::vector<uint8_t> psram, sram;
  uint8_t  snescmd[SNESCMD_SIZE];
  uint32_t cursor, rom_mask, ram_mask;
  uint8_t  ram_base, map;
  uint16_t features, status;

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
        else if (tx == 0xf1) { phase = PH_STATUS; status_idx = 2; }                 // GETSTATUS
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
      case PH_TEST: return 0xa5;
      case PH_STATUS: { uint8_t v = (status_idx == 2) ? (status >> 8) : (status & 0xff);
                        if (--status_idx == 0) phase = PH_SKIP; return v; }
      case PH_SKIP: default: return 0;
    }
  }

  // SNESCMD: janela $2A00-$2FFF em $00-$3F/$80-$BF (address.v:298), idx = addr&0x3FF.
  bool snescmd_window(uint32_t a) const {
    return ((a & 0x400000u) == 0) && ((a & 0xF800u) == 0x2800u) && ((a & 0x0600u) != 0);
  }
  bool snescmd_accessible() const { return (map == 7) || (features & FEAT_CMD_UNLOCK); }

  // decode unificado: rw=0 read (retorna byte), rw=1 write (usa d).
  // NOTA: regiões de SRAM do mapper "menu" (7) são uma 1ª aproximação; serão afinadas
  // contra address.v na integração com o menu (M2.C).
  uint8_t decode(uint32_t a, int rw, uint8_t d) {
    a &= 0xFFFFFF;
    if (snescmd_window(a) && snescmd_accessible()) {
      uint16_t i = a & (SNESCMD_SIZE - 1);
      if (rw && (i == 0x200 || i == 0x202)) trace_cmd("SNES", "write", i, d);   // $2A00/$2A02
      if (rw) { snescmd[i] = d; return 0; }
      return snescmd[i];
    }
    uint8_t bank = (a >> 16) & 0xff;
    uint16_t off = a & 0xffff;
    if (map == 7 && !(bank & 0x40) && (off & 0xfffe) == 0x2800) {   // S-RTC do menu
      if (off == 0x2800) return rw ? 0 : srtc_read();
      if (rw && (d & 0x0f) == 0x0d) srtc_ptr = 15;                   // $2801: modo leitura
      return 0;
    }
    bool is_sram = false; uint32_t sram_off = 0, pa = 0;

    if (map == 7) {
      // Menu mapper: janela HiROM baseada em SRAM_MENU_ADDR (0xC00000). A base é
      // somada APÓS o rom_mask (senão o mask 0x3FFFFF apagaria a base). Cobre ROM do
      // menu ($C0:xxxx), CFG ($FF0100) e status ($FF1000) - tudo em PSRAM.
      pa = MENU_BASE + ((a & 0x3FFFFF) & rom_mask);
    } else if (map == 1) {                       // LoROM
      if (((bank & 0x7f) >= 0x70) && (off < 0x8000)) { is_sram = true; sram_off = ((bank & 0x0f) << 15) | off; }
      else pa = (((((uint32_t)(bank & 0x7f)) << 15) | (off & 0x7fff)) & rom_mask);
    } else {                                     // HiROM(0)/ExHiROM(2): base 0 (SRAM_ROM_ADDR)
      bool hi_sram = (((bank & 0x7f) >= 0x20) && ((bank & 0x7f) <= 0x3f) && (off >= 0x6000) && (off < 0x8000));
      if (hi_sram) { is_sram = true; sram_off = (a & SRAM_MASK); }
      else pa = (a & 0x3FFFFF) & rom_mask;
    }

    if (is_sram) {
      uint32_t i = (sram_off + ((uint32_t)ram_base << 13)) & ram_mask & SRAM_MASK;
      if (rw) { sram[i] = d; return 0; }
      return sram[i];
    }
    pa &= PSRAM_MASK;
    if (rw) { psram[pa] = d; return 0; }
    return psram[pa];
  }
};

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
}
