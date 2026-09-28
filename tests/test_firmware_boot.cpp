// Ciclone - firmware boot smoke test (M2, par A/A).
//
// Runs the REAL sd2snes firmware (libsd2snesfw.a, main() renamed
// ciclone_fw_main) on the host against the behavioral FpgaModel and a FAT32 SD
// image, and proves it boots: configures the FPGA, streams /sd2snes/m3nu.bin
// into PSRAM, forces mapper 7, hands the menu MCU_CMD_RDY (0x55), and verifies
// PSRAM before entering the menu command loop.
//
// The firmware main loop never returns (it polls the SNES via SNESCMD forever,
// and there is no SNES here), so we run it in a thread under a wall-clock
// watchdog. A TracingModel decorator wraps the behavioral model and decodes the
// SPI byte stream into high-level commands for the trace + milestone checks; it
// forwards every call to the real behavioral model so behaviour is unchanged
// (behavioral.cpp stays untouched).

#include "fpga_model.h"
#include "ciclone_seam.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <pthread.h>
#include <unistd.h>
#include <vector>

using namespace ciclone;

extern "C" int  ciclone_fw_main(void);
extern "C" void ciclone_set_uart_echo(int on);

// ---- milestones we want to observe -----------------------------------------
struct Milestones {
  std::atomic<int> fpga_pgm{0};         // model reconfigure (FPGA "programmed")
  std::atomic<int> set_mapper7{0};      // SETMAPPER 7 (menu mapper)
  std::atomic<int> set_rommask{0};      // SETROMMASK
  std::atomic<uint64_t> psram_dma{0};   // bytes streamed SD->PSRAM (offload)
  std::atomic<int> snescmd_rdy{0};      // wrote 0x55 (MCU_CMD_RDY) to $2A02
  std::atomic<int> snescmd_writes{0};
  std::atomic<int> menu_loop_polls{0};  // reads of MCU_CMD ($2A00) = in menu loop
  std::atomic<uint64_t> spi_bytes{0};
};
static Milestones g_ms;

// fpga_pgm() in the host shim calls ciclone_fpga_reconfigure -> model->reconfigure.
// Count reconfigures by also hooking that symbol.
extern "C" void ciclone_fpga_reconfigure(const char *core);   // provided by glue
static void (*real_reconf)(const char *) = nullptr;

// ---- trace log -------------------------------------------------------------
static std::mutex      g_log_mtx;
static std::vector<std::string> g_log;
static void logline(const std::string &s) {
  std::lock_guard<std::mutex> lk(g_log_mtx);
  if (g_log.size() < 4000) g_log.push_back(s);
}
static char hexbuf[64];
static const char *h2(uint32_t v) { snprintf(hexbuf, sizeof(hexbuf), "0x%02x", v & 0xff); return hexbuf; }

// SNESCMD address labels (snes.h)
static const char *snescmd_label(uint16_t a) {
  switch (a) {
    case 0x2a00: return "MCU_CMD";
    case 0x2a02: return "SNES_CMD";
    case 0x2a04: return "MCU_PARAM";
    case 0x2be0: return "SFX_MAILBOX";
    default:     return "";
  }
}

// ---- TracingModel: decode the SPI stream, forward to the behavioral model ---
class TracingModel : public FpgaModel {
public:
  explicit TracingModel(FpgaModel *inner) : in_(inner) {}

  // SNES side (unused here) - forward.
  uint8_t snes_read(uint32_t a) override { return in_->snes_read(a); }
  void    snes_write(uint32_t a, uint8_t d) override { in_->snes_write(a, d); }
  void    tick(int c) override { in_->tick(c); }

  void reset() override { in_->reset(); }
  void reconfigure(int core) override {
    g_ms.fpga_pgm++;
    logline("FPGA reconfigure (fpga_pgm) -> model reset SNESCMD");
    in_->reconfigure(core);
  }

  uint8_t *psram_ptr() override { return in_->psram_ptr(); }
  uint8_t  peek_snescmd(uint16_t off) override { return in_->peek_snescmd(off); }
  uint8_t  mapper() override { return in_->mapper(); }
  int      mcu_rdy() override { return in_->mcu_rdy(); }

  void dma_write(const uint8_t *buf, uint32_t len) override {
    g_ms.psram_dma += len;
    if (dma_logs_++ < 8)
      logline(std::string("SD->PSRAM DMA ") + std::to_string(len) + " bytes @cursor (offload)");
    in_->dma_write(buf, len);
  }

  // MCU side - this is where we decode commands.
  void spi_select() override { ph_ = CMD; in_->spi_select(); }
  void spi_deselect() override {
    flush_pending();
    in_->spi_deselect();
  }

  uint8_t spi_txrx(uint8_t tx) override {
    g_ms.spi_bytes++;
    decode(tx);
    return in_->spi_txrx(tx);
  }

private:
  FpgaModel *in_;

  enum Phase { CMD, ADDR, ROMMASK, RAMMASK, MEM_W, MEM_R, SC_ADDR, SC_W, SC_R, SKIP };
  int      ph_ = CMD;
  int      cnt_ = 0;
  uint32_t acc_ = 0;
  uint16_t sc_addr_ = 0;
  int      sc_idx_ = 0;
  uint8_t  cmd_byte_ = 0;
  int      mem_w_count_ = 0, mem_r_count_ = 0;
  int      dma_logs_ = 0;
  bool     pending_ = false;
  std::string pending_msg_;

  void emit(const std::string &m) { pending_ = true; pending_msg_ = m; }
  void flush_pending() {
    if (pending_) { logline(pending_msg_); pending_ = false; }
    // collapse run-length of mem writes/reads into one line at deselect
    if (ph_ == MEM_W && mem_w_count_ > 0)
      logline("  WRITEMEM x" + std::to_string(mem_w_count_));
    if (ph_ == MEM_R && mem_r_count_ > 0)
      logline("  READMEM x" + std::to_string(mem_r_count_));
    mem_w_count_ = mem_r_count_ = 0;
  }

  void decode(uint8_t tx) {
    switch (ph_) {
      case CMD: {
        cmd_byte_ = tx;
        uint8_t hi = tx & 0xf0;
        if (tx == 0x00) { ph_ = ADDR; cnt_ = 3; acc_ = 0; }
        else if (tx == 0x10) { ph_ = ROMMASK; cnt_ = 3; acc_ = 0; }
        else if (tx == 0x20) { ph_ = RAMMASK; cnt_ = 3; acc_ = 0; }
        else if (hi == 0x30) { uint8_t m = tx & 0x0f; emit(std::string("SETMAPPER ") + std::to_string(m));
                               if (m == 7) g_ms.set_mapper7++; ph_ = SKIP; }
        else if (hi == 0x40) { emit("SDDMA trigger"); ph_ = SKIP; }
        else if (hi == 0x80) { ph_ = MEM_R; mem_r_count_ = 0; }
        else if (hi == 0x90) { ph_ = MEM_W; mem_w_count_ = 0; }
        else if (tx == 0xd0) { ph_ = SC_ADDR; cnt_ = 2; acc_ = 0; sc_idx_ = 0; }
        else if (tx == 0xd1) { ph_ = SC_R; }
        else if (tx == 0xd2) { ph_ = SC_W; sc_idx_ = 0; }
        else if (tx == 0xf0) { emit("TEST (alive?)"); ph_ = SKIP; }
        else if (tx == 0xf1) { emit("GETSTATUS"); ph_ = SKIP; }
        else { emit(std::string("cmd ") + h2(tx)); ph_ = SKIP; }
        break;
      }
      case ADDR:
        acc_ = (acc_ << 8) | tx;
        if (--cnt_ == 0) { snprintf(hexbuf, sizeof(hexbuf), "SETADDR 0x%06x", acc_ & 0xffffff);
                           emit(hexbuf); ph_ = SKIP; }
        break;
      case ROMMASK:
        acc_ = (acc_ << 8) | tx;
        if (--cnt_ == 0) { g_ms.set_rommask++; snprintf(hexbuf, sizeof(hexbuf), "SETROMMASK 0x%06x", acc_ & 0xffffff);
                           emit(hexbuf); ph_ = SKIP; }
        break;
      case RAMMASK:
        acc_ = (acc_ << 8) | tx;
        if (--cnt_ == 0) { snprintf(hexbuf, sizeof(hexbuf), "SETRAMMASK 0x%06x", acc_ & 0xffffff);
                           emit(hexbuf); ph_ = SKIP; }
        break;
      case MEM_W: mem_w_count_++; break;
      case MEM_R: mem_r_count_++; break;
      case SC_ADDR:
        acc_ |= (uint32_t)tx << (8 * sc_idx_); sc_idx_++;
        if (--cnt_ == 0) {
          sc_addr_ = acc_ & 0xffff;
          if (cmd_byte_ == 0xd0 && (sc_addr_ == 0x2a00)) g_ms.menu_loop_polls++;
          ph_ = SKIP;
        }
        break;
      case SC_W:
        if (sc_idx_ == 0) {
          g_ms.snescmd_writes++;
          const char *lbl = snescmd_label(sc_addr_);
          char m[96]; snprintf(m, sizeof(m), "SNESCMD write [%s%s0x%04x] = %s",
                               lbl, *lbl ? " " : "", sc_addr_, h2(tx));
          emit(m);
          if (sc_addr_ == 0x2a02 && tx == 0x55) g_ms.snescmd_rdy++;  // MCU_CMD_RDY
          sc_addr_++;
        }
        sc_idx_++;
        break;
      case SC_R: {
        const char *lbl = snescmd_label(sc_addr_);
        char m[96]; snprintf(m, sizeof(m), "SNESCMD read  [%s%s0x%04x]",
                             lbl, *lbl ? " " : "", sc_addr_);
        emit(m);
        sc_addr_++;
        break;
      }
      case SKIP: default: break;
    }
  }
};

// ---- watchdog: the firmware loops forever; stop after the boot window ------
static void *fw_thread(void *) {
  ciclone_fw_main();           // never returns; killed at process exit
  return nullptr;
}

int main(int argc, char **argv) {
  const char *img = (argc > 1) ? argv[1] : "build/sdcard.img";
  int watchdog_ms = (argc > 2) ? atoi(argv[2]) : 8000;
  // Silence the firmware's (very chatty, unbuffered) UART console so it doesn't
  // dominate runtime; our own decoded trace is the signal. Pass a 3rd arg to keep it.
  if (argc <= 3) ciclone_set_uart_echo(0);
  setvbuf(stdout, nullptr, _IOLBF, 0);

  printf("== ciclone firmware boot smoke test ==\n");
  printf("image: %s   watchdog: %d ms\n\n", img, watchdog_ms);

  FpgaModel *behavioral = make_behavioral_model();
  TracingModel *tracer = new TracingModel(behavioral);
  set_active_model(tracer);

  if (ciclone_sd_open(img) != 0) {
    fprintf(stderr, "FATAL: could not open SD image %s\n", img);
    return 2;
  }

  // Run the firmware boot in a thread; watch the wall clock.
  pthread_t th;
  if (pthread_create(&th, nullptr, fw_thread, nullptr) != 0) {
    fprintf(stderr, "FATAL: pthread_create failed\n");
    return 2;
  }

  // Poll milestones; finish early once we've seen the full boot handshake.
  int waited = 0;
  const int step = 25;
  int last_report = 0;
  while (waited < watchdog_ms) {
    usleep(step * 1000);
    waited += step;
    if (waited - last_report >= 1000) {
      last_report = waited;
      fprintf(stderr, "[wd %dms] spi=%llu pgm=%d map7=%d rommask=%d dma=%llu "
              "scWrites=%d rdy=%d polls=%d\n", waited,
              (unsigned long long)g_ms.spi_bytes.load(), g_ms.fpga_pgm.load(),
              g_ms.set_mapper7.load(), g_ms.set_rommask.load(),
              (unsigned long long)g_ms.psram_dma.load(), g_ms.snescmd_writes.load(),
              g_ms.snescmd_rdy.load(), g_ms.menu_loop_polls.load());
    }
    if (g_ms.snescmd_rdy.load() && g_ms.menu_loop_polls.load() >= 2 &&
        g_ms.set_mapper7.load()) {
      // Full boot reached + menu loop running: give it a moment, then stop.
      usleep(150 * 1000);
      break;
    }
  }

  // Snapshot + print the trace.
  printf("\n---- SPI / SNESCMD command trace (firmware -> FpgaModel) ----\n");
  {
    std::lock_guard<std::mutex> lk(g_log_mtx);
    size_t shown = 0;
    for (auto &l : g_log) { printf("  %s\n", l.c_str()); if (++shown >= 120) { printf("  ... (%zu more)\n", g_log.size() - shown); break; } }
  }

  printf("\n---- milestones ----\n");
  printf("  SPI bytes to model      : %llu\n", (unsigned long long)g_ms.spi_bytes.load());
  printf("  FPGA reconfigure(s)     : %d   %s\n", g_ms.fpga_pgm.load(), g_ms.fpga_pgm.load() ? "[OK]" : "[--]");
  printf("  SETROMMASK              : %d   %s\n", g_ms.set_rommask.load(), g_ms.set_rommask.load() ? "[OK]" : "[--]");
  printf("  SETMAPPER 7 (menu)      : %d   %s\n", g_ms.set_mapper7.load(), g_ms.set_mapper7.load() ? "[OK]" : "[--]");
  printf("  SD->PSRAM bytes (m3nu)  : %llu   %s\n", (unsigned long long)g_ms.psram_dma.load(),
         g_ms.psram_dma.load() ? "[OK]" : "[--]");
  printf("  SNESCMD writes          : %d\n", g_ms.snescmd_writes.load());
  printf("  MCU_CMD_RDY (0x55->$2A02): %d   %s\n", g_ms.snescmd_rdy.load(), g_ms.snescmd_rdy.load() ? "[OK]" : "[--]");
  printf("  menu loop MCU_CMD polls : %d   %s\n", g_ms.menu_loop_polls.load(),
         g_ms.menu_loop_polls.load() >= 2 ? "[OK]" : "[--]");
  printf("  model mapper now        : %u\n", behavioral->mapper());

  // Verify the menu image really landed in PSRAM: m3nu.bin starts at
  // SRAM_MENU_ADDR (0xC00000). load_rom offsets by romprops.load_address; for a
  // headerless 128 KB LoROM-ish menu that is 0, so byte 0 of the file should be
  // at PSRAM[0xC00000 & PSRAM_MASK] = PSRAM[0x000000]. Just check PSRAM is not
  // all-zero in the menu region as a sanity signal.
  // Menu lands at SRAM_MENU_ADDR (0xC00000) masked to 24-bit PSRAM (0xC00000).
  uint8_t *ps = behavioral->psram_ptr();
  int nonzero = 0;
  if (ps) for (uint32_t i = 0xC00000; i < 0xC20000; i++) if (ps[i]) { nonzero++; }
  printf("  PSRAM menu region nonzero bytes (@0xC00000,128KB): %d   %s\n", nonzero, nonzero ? "[OK]" : "[--]");

  // The menu image reaches PSRAM either via the SD->PSRAM DMA offload OR via the
  // direct WRITEMEM SPI loop (load_rom picks per path); accept either.
  bool menu_in_psram = (g_ms.psram_dma.load() > 0) || (nonzero > 0);
  bool pass = g_ms.fpga_pgm.load() && g_ms.set_mapper7.load() &&
              menu_in_psram && g_ms.snescmd_rdy.load() &&
              g_ms.menu_loop_polls.load() >= 2;

  printf("\n== %s ==\n", pass ? "BOOT REACHED MENU COMMAND LOOP (PASS)"
                              : "did not reach full boot (see trace)");
  fflush(stdout);
  // Firmware thread is still spinning in the menu loop; exit hard.
  _exit(pass ? 0 : 1);
}
