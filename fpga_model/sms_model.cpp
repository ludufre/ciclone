// Ciclone - the SMS core: real RTL (Verilated sms_core) + the main.v/address.v glue in C++.
//
// What runs as RTL (built by fpga_model/verilate_sms.sh from the firmware tree): sms_core.v
// and everything under it -- the tv80 Z80, the Sega mapper, WRAM, the VDP capture, the PSG
// and the SMS->SNES translation engine. Any change the core gets is tested as it is.
//
// What is mirrored here, line for line from verilog/sd2snes_sms/main.v (search for the
// quoted names there): the CLK2 clock (96 MHz) and the fractional-N SMS clock enable
// (sms_ce_acc, K = 1251194), the PSRAM arbiter that serves the core (the STATE FSM with
// ROM_CYCLE_LEN = 7, the CTX > SMS_RD > SMS_WR priority, the free_slot rule, the request
// latches SMS_RD_PENDr / SMS_WR_PENDr / sms_wr_busy), the pad latch at $EF0000/1 (sms_pad1),
// the double-buffer handshake at $EF0005 (sms_buf_front / sms_ready / TR_GATE) and the
// $E0-$E3 window of address.v (SMS_BUF_HIT). RST = SNES_DEADr: the core sits in reset
// while the SNES is held in reset and restarts on every console reset.
//
// The SNES side of the arbiter is a timing model, not RTL: bsnes does not expose every bus
// cycle, so free slots come from the SNES time. A cart ROM access (each opcode/operand the
// player fetches, each byte a DMA reads from $E0-$E3) is an 8-master-clock SlowROM cycle
// with one free slot at its end (SNES_cycle_end; its start is a ROM_HIT, no free_strobe);
// any other stretch of time gives one slot per CICLONE_SMS_SLOT_MC master clocks (default 3:
// the cycle_start + cycle_end pair of a 6-clock internal/IO cycle). ctx.v's PSRAM mirror is
// the other client the core competes with: every SNES write ctx.v mirrors (WRAM, PPU and
// CPU registers, the VRAM/CGRAM/OAM data ports, the APU ports) queues one CTX write, which
// wins the next free slot, and a second one while it is pending is dropped (CTX_RDY).
// Register READS ctx.v also mirrors ($421x, $2134-$213F) are not visible from bsnes.
//
// main.v variants recognised in the tree (verilate_sms.sh -> vsms_glue.h, shown as glue= in the
// counters): "ctxoff" = the ctx instance gets BUS_RDY 0 (no mirror writes at all); "fair" = the
// arbiter serves the core ABOVE the MCU, and alternates SMS_RD / SMS_WR when both wait
// (sms_rd_last). Anything else changed in main.v around the core is NOT followed here.
#include "sms_model.h"
#include "Vsms_core.h"
#include "Vsms_core___024root.h"
#include "vsms_clk.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cstddef>
#include <vector>
#include <deque>
#include "vsms_snap.h"
#include "vsms_mem.h"
#include "vsms_glue.h"

// libverilated wants it (legacy time API); this model counts its own cycles
double __attribute__((weak)) sc_time_stamp() { return 0; }

// One CLK2 edge costs two evals the canonical way (CLK=1, then CLK=0 so the next 1 is an
// edge). The design has no negedge logic, so the falling half only exists to update
// Verilator's edge detector: we lower CLK and its "previous value" by hand and call the
// scheduler directly (eval_step adds per-call bookkeeping for $display/threads this design
// does not use). The detectors are found in the generated code by verilate_sms.sh
// (vsms_clk.h); when it finds none, CICLONE_SMS_SAFE_EVAL goes back to the canonical pair.
void Vsms_core___024root___eval(Vsms_core___024root* vlSelf);

namespace ciclone {
namespace {

constexpr double CLK2_HZ = 96e6;
constexpr double MC_HZ = 21477272.7;                 // SNES master clock (NTSC)
constexpr double CLK2_PER_MC = CLK2_HZ / MC_HZ;      // ~4.47
constexpr uint32_t SMS_K = 1251194;                  // main.v sms_ce_acc step (25-bit)
constexpr int ROM_CYCLE_LEN = 7;
constexpr uint32_t PSRAM_MASK = 0xFFFFFF;
constexpr double MC_PER_LINE = 1364.0;

enum St { IDLE, CTX_ADDR, CTX_END, MCU_ADDR, MCU_END, RD_ADDR, RD_END, WR_ADDR, WR_END };

class SmsVerilated : public SmsCore {
public:
  explicit SmsVerilated(uint8_t *psram) : ps(psram) {
    vctx = new VerilatedContext;
    v = new Vsms_core(vctx);
    if (const char *s = getenv("CICLONE_SMS_SLOT_MC")) slot_mc = atof(s);
    if (slot_mc < 1) slot_mc = 1;
    slot_period = (uint64_t)(slot_mc * CLK2_PER_MC + 0.5);
    double ns_short = 350, ns_long = 1200;
    if (const char *mc = getenv("CICLONE_SMS_MCU")) {
      if (!strcmp(mc, "0")) mcu_on = false;
      else sscanf(mc, "%lf,%lf", &ns_short, &ns_long);
    }
    if (const char *e = getenv("CICLONE_SMS_MCU_SPI_NS")) mcu_spi_ns = atof(e);
    if (const char *e = getenv("CICLONE_SMS_MCU_FIXED_NS")) mcu_fixed_ns = atof(e);
    mcu_gap_short = (uint64_t)(ns_short * 1e-9 * CLK2_HZ + 0.5);
    mcu_gap_long = (uint64_t)(ns_long * 1e-9 * CLK2_HZ + 0.5);
    if (const char *e = getenv("CICLONE_SMS_EXACT")) exact = atoi(e) != 0;
    snap_init();
    if (const char *f = getenv("CICLONE_SMS_LOG")) { log = fopen(f, "w"); if (log) setvbuf(log, nullptr, _IOLBF, 0); }
    power_on();
  }
  ~SmsVerilated() override { if (log) fclose(log); delete v; delete vctx; }

  void power_on() override {
    ce_acc = 0; ce = 0;
    rd_pend = wr_pend = ctx_pend = false; rd_addr = wr_addr = 0; din = wr_data = 0;
    rom_rdy = wack = wr_busy = false; st = IDLE; delay = 0;
    front = ready = false; pad_raw = 0; swap_pulse = false;
    mcu_pend = false; mcu_active = false; mcu_next = 0; mcu_k = 0;
    synced = false; block_from = block_until = 0; ends.clear(); same = 0; snap_ok = false;
    memset(&c, 0, sizeof c); memset(&last, 0, sizeof last);
    tr_busy_prev = false; tr_t0 = 0; tr_bytes = 0; nmi_mc = 0; nmi_open = false;
    hold_reset();
  }
  void snes_reset() override { hold_reset(); }

  void run_to(uint64_t mc) override {
    if (!synced) { synced = true; mc0 = mc; cyc0 = cyc; return; }   // first look at the SNES clock
    if (mc < mc0) return;
    uint64_t target = cyc0 + (uint64_t)((double)(mc - mc0) * CLK2_PER_MC);
    while (cyc < target) step();
  }
  void cart_cycle(uint64_t mc) override {
    // the access lands 4 clocks before the end of its 8-clock cycle (bsnes op_read)
    run_to(mc >= 4 ? mc - 4 : 0);
    if (!synced) return;
    uint64_t beg = to_cyc(mc >= 4 ? mc - 4 : 0), end = to_cyc(mc + 4);
    if (beg > block_until || block_until <= cyc) block_from = beg;    // a new run of ROM_HIT cycles
    if (end > block_until) block_until = end;
    if (ends.empty() || ends.back() < end) ends.push_back(end);       // its SNES_cycle_end slot
    // (a ROM_HIT cycle only matters to a pending request, and a pending request is never idle)
  }
  void ctx_write(uint64_t mc) override {
    run_to(mc);
    if (ctx_off) return;                               // main.v without the ctx mirror
    if (ctx_pend) c.ctx_drop++; else ctx_pend = true;
  }
  uint8_t buf_read(uint32_t a) override {
    // address.v: SMS_BUF_HIT ($E0-$E3) -> sms_set_base + sms_sel_off + A[15:0]
    static const uint32_t sel[4] = {0x00000, 0x04000, 0x04800, 0x05000};
    uint32_t base = front ? 0x390000 : 0x380000;
    return ps[(base + sel[(a >> 16) & 3] + (a & 0xFFFF)) & PSRAM_MASK];
  }
  void ctl_write(uint32_t a, uint8_t d) override {
    if ((a & 0xFE) == 0x00) {                       // $EF0000 JOY1L / $EF0001 JOY1H
      if (a & 1) pad_raw = (pad_raw & 0x00FF) | d << 8; else pad_raw = (pad_raw & 0xFF00) | d;
    }
    if ((a & 0xFF) == 0x05) swap_pulse = true;     // $EF0005: consumed on the next CLK2
  }
  void nmi(uint64_t mc) override { run_to(mc); nmi_pulse = true; nmi_mc = mc; nmi_open = true; c.nmis++; }
  void mcu_load(double psram, double spi) override {
    mcu_active = mcu_on && psram >= 1;
    if (!mcu_active) return;
    mcu_burst = (uint64_t)(psram + 0.5);
    // the rest of the pass: its other SPI bytes (a PSRAM read costs ~2.25 of them in a readlong)
    // at the SPI byte time, plus the C around them
    double other = spi - psram * 2.25; if (other < 0) other = 0;
    mcu_idle = (uint64_t)((other * mcu_spi_ns + mcu_fixed_ns) * 1e-9 * CLK2_HZ + 0.5);
    c.mcu_pass_reads = mcu_burst; c.mcu_pass_idle = mcu_idle;
  }
  void screen_on(uint64_t mc) override {
    if (!nmi_open) return;
    nmi_open = false;
    uint64_t lines = (uint64_t)((double)(mc - nmi_mc) / MC_PER_LINE + 0.5);
    c.nmi_lines_sum += lines;
    if (lines > c.nmi_lines_max) c.nmi_lines_max = lines;
    if (lines > 37) c.nmi_overrun++;               // NTSC VBlank = lines 225..261
    last_nmi_lines = lines;
  }
  void snes_frame(uint64_t mc) override {
    run_to(mc);
    c.snes_frames++;
    if (!log) return;
    Counters d = c;
    auto df = [&](uint64_t Counters::*f) { return (unsigned long long)(d.*f - last.*f); };
    unsigned long long ce_d = df(&Counters::ce);
    fprintf(log, "f=%llu sms=%llu tr=%llu busy=%llu gate=%llu shown=%llu empty=%llu "
                 "wrom=%.1f%% wwram=%.1f%% trmax=%llu bytes=%llu nmi=%llu ctx=%llu mcu=%llu rd=%llu wr=%llu drop=%llu pc=%04x\n",
            (unsigned long long)c.snes_frames, df(&Counters::sms_frames), df(&Counters::tr_started),
            df(&Counters::tr_skip_busy), df(&Counters::tr_skip_gate), df(&Counters::shown), df(&Counters::swap_empty),
            ce_d ? 100.0 * df(&Counters::ce_wait_rom) / ce_d : 0.0, ce_d ? 100.0 * df(&Counters::ce_wait_wram) / ce_d : 0.0,
            (unsigned long long)frame_tr_max, df(&Counters::tr_bytes), (unsigned long long)last_nmi_lines,
            df(&Counters::g_ctx), df(&Counters::g_mcu), df(&Counters::g_rd), df(&Counters::g_wr), df(&Counters::ctx_drop), (unsigned)v->DBG_PC);
    last = c; frame_tr_max = 0;
  }
  int peek(const char *space, uint32_t addr, uint8_t *out, int n) override {
    Vsms_core___024root *r = v->rootp;
#define VSMS_PEEK(name, m) \
    if (!strcmp(space, #name)) { \
      const int size = (int)(sizeof(r->m) / sizeof(r->m[0])); \
      for (int i = 0; i < n; i++) out[i] = (uint8_t)r->m[(addr + i) % size]; \
      return n; \
    }
    VSMS_MEMS(VSMS_PEEK)
#undef VSMS_PEEK
    if (!strcmp(space, "bank")) {
      uint8_t b[8] = {}; int k = 0;
#define VSMS_BANK(m) b[k++] = r->m;
      VSMS_BANKS(VSMS_BANK)
#undef VSMS_BANK
      for (int i = 0; i < n; i++) out[i] = (addr + i) < (uint32_t)k ? b[addr + i] : 0;
      return n;
    }
    if (!strcmp(space, "pc")) {
      uint16_t pc = v->DBG_PC;
      for (int i = 0; i < n; i++) out[i] = (addr + i) == 0 ? pc & 0xff : (addr + i) == 1 ? pc >> 8 : 0;
      return n;
    }
    return -1;
  }
  int stats(char *buf, int n) override {
    double secs = c.snes_frames / 60.0988;
    return snprintf(buf, n,
      "snes_frames=%llu sms_frames=%llu tr_started=%llu tr_skip_busy=%llu tr_skip_gate=%llu tr_done=%llu "
      "shown=%llu swap_empty=%llu shown_fps=%.2f sms_fps=%.2f z80_ce=%llu z80_wait_rom=%llu z80_wait_wram=%llu "
      "tr_cycles_max=%llu tr_cycles_avg=%llu tr_bytes=%llu nmis=%llu nmi_lines_max=%llu nmi_lines_avg=%.1f "
      "nmi_overrun=%llu grant_ctx=%llu grant_mcu=%llu grant_rd=%llu grant_wr=%llu ctx_drop=%llu rd_wait=%llu wr_wait=%llu "
      "glue=%s mcu_pass_reads=%llu mcu_pass_idle=%llu pc=%04x vram_writes=%u display_on=%d front=%d clk2=%llu coasted=%llu",
      u(c.snes_frames), u(c.sms_frames), u(c.tr_started), u(c.tr_skip_busy), u(c.tr_skip_gate), u(c.tr_done),
      u(c.shown), u(c.swap_empty), secs > 0 ? c.shown / secs : 0.0, secs > 0 ? c.sms_frames / secs : 0.0,
      u(c.ce), u(c.ce_wait_rom), u(c.ce_wait_wram),
      u(c.tr_cycles_max), u(c.tr_done ? c.tr_cycles_sum / c.tr_done : 0), u(c.tr_bytes), u(c.nmis),
      u(c.nmi_lines_max), c.nmis ? (double)c.nmi_lines_sum / c.nmis : 0.0, u(c.nmi_overrun),
      u(c.g_ctx), u(c.g_mcu), u(c.g_rd), u(c.g_wr), u(c.ctx_drop), u(c.rd_wait), u(c.wr_wait),
      prio_sms ? (ctx_off ? "fair,ctxoff" : "fair") : (ctx_off ? "ctxoff" : "master"),
      u(c.mcu_pass_reads), u(c.mcu_pass_idle), (unsigned)v->DBG_PC, (unsigned)v->DBG_VRAM_WRITES, (int)v->DBG_DISPLAY_ON, (int)front, u(cyc), u(c.coasted));
  }

private:
  static unsigned long long u(uint64_t x) { return (unsigned long long)x; }
  uint8_t *ps;
  VerilatedContext *vctx;
  Vsms_core *v;
  FILE *log = nullptr;
  double slot_mc = 8.0;

  // ---- the MCU's PSRAM traffic (MCU_RD_PENDr: above the core in the arbiter) ----
  // The firmware's game loop calls sram_reliable() on every pass: 256 sram_readlong() of the
  // scratchpad, back to back -- each a set-address (4 SPI bytes), the read command and 4 data
  // bytes, every data byte a PSRAM read the arbiter serves BEFORE the core's. The host MCU
  // runs at whatever speed the Mac gives it, so only the SHAPE of a pass comes from it
  // (PSRAM bytes and SPI bytes per pass, Behavioral::snes_frame); the time comes from the
  // hardware: SPI at 48 MHz (96 MHz PCLK / SSP_CLK_DIVISOR 2) = 167 ns a byte plus the
  // polling around it -> a read every ~350 ns inside a readlong, ~1.2 us between readlongs,
  // and the rest of the pass at CICLONE_SMS_MCU_SPI_NS (default 250) per other SPI byte plus
  // CICLONE_SMS_MCU_FIXED_NS (default 2000) of C. A firmware that polls less (Xeno Crisis
  // reads 4 longs, not 256) gets a lighter load here by itself.
  // CICLONE_SMS_MCU="<short ns>,<long ns>" changes the read spacing, "0" turns it all off.
  FILE *trace = getenv("CICLONE_SMS_TRACE") ? fopen(getenv("CICLONE_SMS_TRACE"), "w") : nullptr; bool nmi_pulse = false;
  bool rd_last = false;
  // the "fair" main.v (vsms_glue.h, or forced with CICLONE_SMS_PRIO=1): the core ABOVE the MCU,
  // SMS_RD / SMS_WR alternating when both wait; "ctxoff": the ctx mirror never writes
#ifdef VSMS_GLUE_FAIR
  bool prio_sms = true;
#else
  bool prio_sms = getenv("CICLONE_SMS_PRIO") != nullptr;
#endif
#ifdef VSMS_GLUE_CTX_OFF
  bool ctx_off = true;
#else
  bool ctx_off = getenv("CICLONE_SMS_NOCTX") != nullptr;
#endif
  bool mcu_pend = false, mcu_active = false, mcu_on = true; uint64_t mcu_next = 0, mcu_k = 0;
  uint64_t mcu_gap_short = 0, mcu_gap_long = 0, mcu_burst = 1024, mcu_idle = 0;
  double mcu_spi_ns = 250, mcu_fixed_ns = 2000;

  // ---- main.v glue state (registers) ----
  uint32_t ce_acc; bool ce;
  bool rd_pend, wr_pend, ctx_pend; uint32_t rd_addr, wr_addr; uint8_t din, wr_data;
  bool rom_rdy, wack, wr_busy;
  St st; int delay;
  bool front, ready; uint16_t pad_raw; bool swap_pulse;
  int rst_left = 0;

  // ---- time ----
  uint64_t cyc = 0, cyc0 = 0, mc0 = 0; bool synced;
  uint64_t block_from = 0, block_until;   // ROM_HIT SNES cycles: no free slot inside...
  std::deque<uint64_t> ends;              // ...but one at the end of each of them
  uint64_t slot_period = 13;
  uint64_t to_cyc(uint64_t mc) const { return cyc0 + (uint64_t)((double)(mc - mc0) * CLK2_PER_MC); }

  // ---- counters ----
  struct Counters {
    uint64_t snes_frames, sms_frames, tr_started, tr_skip_busy, tr_skip_gate, tr_done;
    uint64_t shown, swap_empty, ce, ce_wait_rom, ce_wait_wram;
    uint64_t tr_cycles_max, tr_cycles_sum, tr_bytes, nmis, nmi_lines_max, nmi_lines_sum, nmi_overrun;
    uint64_t g_ctx, g_rd, g_wr, ctx_drop, rd_wait, wr_wait, coasted, g_mcu, mcu_pass_reads, mcu_pass_idle;
  } c, last;
  bool tr_busy_prev; uint64_t tr_t0, tr_bytes, frame_tr_max = 0;
  uint64_t nmi_mc; bool nmi_open; uint64_t last_nmi_lines = 0;

  void hold_reset() { rst_left = 16; same = 0; snap_ok = false; frozen = false; prev_in = ~0ull; }
  bool did_eval = false;
  void clock_edge() {
#ifdef CICLONE_SMS_SAFE_EVAL
    v->CLK = 1; v->eval(); v->CLK = 0; v->eval();
#else
    if (!did_eval) { did_eval = true; v->CLK = 0; v->eval(); }   // initial/settle once
    Vsms_core___024root *r = v->rootp;
    r->CLK = 1;
    Vsms_core___024root___eval(r);
    r->CLK = 0; VSMS_CLK_FALL(r);
#endif
  }

  uint8_t pad1() const {                         // main.v sms_pad1 (active low)
    uint16_t r = pad_raw;
    auto b = [&](int i) { return (r >> i) & 1; };
    uint8_t p = (uint8_t)(((b(14) | b(7)) << 5) | ((b(15) | b(7)) << 4) | (b(8) << 3) | (b(9) << 2) | (b(10) << 1) | b(11));
    return (uint8_t)~p;
  }

  bool free_slot() {
    while (!ends.empty() && ends.front() < cyc) ends.pop_front();
    if (!ends.empty() && ends.front() == cyc) { ends.pop_front(); return true; }   // SNES_cycle_end
    if (cyc >= block_from && cyc < block_until) return false;                     // inside ROM_HIT cycles
    return cyc % slot_period == 0;                 // cycle_start (free_strobe) + cycle_end of the rest
  }

  // ---- skipping the evaluation of cycles that cannot change the core ----
  // Between two Z80 clock enables (~27 CLK2 apart), and while a PSRAM access the core waits
  // for is in flight, the core usually sits still. After two consecutive edges with the same
  // inputs that left every register of the core unchanged (the Verilated state minus the big
  // memories, which only change through those registers), every further edge with the same
  // inputs is the same no-op: the core is "frozen" and only the C++ glue runs (the arbiter
  // counting, the clock-enable accumulator) until one of the core's inputs changes.
  // CICLONE_SMS_EXACT=1 evaluates every edge (same results, ~2.5x slower;
  // tests/sms_bench.cpp checks that the two agree).
  bool exact = false;
  int same; bool snap_ok;
  std::vector<std::pair<size_t, size_t>> snap_ranges;
  std::vector<uint8_t> snap_prev;
  void snap_init() {
    const size_t n = sizeof(Vsms_core___024root);
    std::vector<std::pair<size_t, size_t>> big;
#define VSMS_BIG_ONE(m) big.push_back({offsetof(Vsms_core___024root, m), sizeof(((Vsms_core___024root *)nullptr)->m)});
    VSMS_BIG_MEMBERS(VSMS_BIG_ONE)
#undef VSMS_BIG_ONE
    std::sort(big.begin(), big.end());
    size_t at = 0;
    for (auto &b : big) { if (b.first > at) snap_ranges.push_back({at, b.first - at}); at = b.first + b.second; }
    if (n > at) snap_ranges.push_back({at, n - at});
    size_t tot = 0; for (auto &r : snap_ranges) tot += r.second;
    snap_prev.assign(tot, 0);
  }
  bool snap_same_and_save() {
    const uint8_t *base = (const uint8_t *)v->rootp; uint8_t *d = snap_prev.data(); bool eq = true;
    for (auto &r : snap_ranges) {
      if (eq && memcmp(d, base + r.first, r.second)) eq = false;
      if (!eq) memcpy(d, base + r.first, r.second);
      d += r.second;
    }
    return eq;
  }
  bool frozen = false; uint64_t frozen_in = 0, prev_in = ~0ull;

  // one CLK2 cycle: glue next-state from the current registers and the core's outputs,
  // posedge of the core with the CURRENT glue registers as its inputs, then commit.
  void step() {
    bool rst = rst_left > 0;
    if (rst) rst_left--;
    // core outputs as of the previous edge
    bool rrq = v->ROM_RRQ, wrq = v->BUF_WRQ, fdone = v->FRAME_DONE;
    uint32_t raddr = v->ROM_ADDR, baddr = v->BUF_ADDR; uint8_t bdata = v->BUF_DATA;

    // ---- request latches ----
    bool n_rd_pend = rd_pend, n_wr_pend = wr_pend, n_ctx_pend = ctx_pend, n_wr_busy = wr_busy;
    bool n_rom_rdy = false, n_wack = false;
    uint32_t n_rd_addr = rd_addr, n_wr_addr = wr_addr; uint8_t n_wr_data = wr_data, n_din = din;
    if (rrq && !rd_pend) { n_rd_pend = true; n_rd_addr = (0x300000 + raddr) & PSRAM_MASK; }
    else if (st == RD_END) { n_rd_pend = false; n_rom_rdy = true; }
    if (wrq && !wr_pend && !wr_busy) {
      n_wr_pend = true; n_wr_addr = ((front ? 0x180000 : 0x190000) + baddr) & PSRAM_MASK; n_wr_data = bdata;
    } else if (st == WR_END) { n_wr_pend = false; n_wack = true; n_wr_busy = true; }
    if (wr_busy && !wrq) n_wr_busy = false;
    if (st == CTX_END) n_ctx_pend = false;
    // the MCU's PSRAM reads (see mcu_load): one at a time, the next one a gap after the last
    if (st == MCU_END) {
      mcu_pend = false;
      ++mcu_k;
      mcu_next = cyc + ((mcu_k & 3) ? mcu_gap_short : mcu_gap_long);
      if (mcu_k >= mcu_burst) { mcu_k = 0; mcu_next += mcu_idle; }   // end of the pass's reads
    } else if (!mcu_pend && mcu_active && cyc >= mcu_next) mcu_pend = true;

    // ---- the STATE FSM (only the clients that exist under the player) ----
    St n_st = st; int n_delay = delay;
    switch (st) {
      case IDLE:
        if (free_slot()) {
          if (ctx_pend)     { n_st = CTX_ADDR; n_delay = ROM_CYCLE_LEN; c.g_ctx++; }
          else if (prio_sms && rd_pend && !(wr_pend && rd_last)) { n_st = RD_ADDR;  n_delay = ROM_CYCLE_LEN; c.g_rd++; rd_last = true; }
          else if (prio_sms && wr_pend) { n_st = WR_ADDR;  n_delay = ROM_CYCLE_LEN; c.g_wr++; rd_last = false; }
          // (the master main.v: the MCU above the core, SMS_RD always before SMS_WR)
          else if (mcu_pend) { n_st = MCU_ADDR; n_delay = ROM_CYCLE_LEN; c.g_mcu++; }
          else if (rd_pend) { n_st = RD_ADDR;  n_delay = ROM_CYCLE_LEN; c.g_rd++; }
          else if (wr_pend) { n_st = WR_ADDR;  n_delay = ROM_CYCLE_LEN; c.g_wr++; }
        }
        break;
      case CTX_ADDR: case MCU_ADDR: case RD_ADDR: case WR_ADDR:
        n_delay = delay - 1;
        if (delay == 0) n_st = st == CTX_ADDR ? CTX_END : st == MCU_ADDR ? MCU_END : st == RD_ADDR ? RD_END : WR_END;
        if (st == RD_ADDR) n_din = ps[rd_addr];
        if (st == WR_ADDR) ps[wr_addr] = wr_data;
        break;
      default: n_st = IDLE; break;
    }
    if (rd_pend) c.rd_wait++;
    if (wr_pend) c.wr_wait++;

    // ---- double buffer ----
    bool swap = swap_pulse; swap_pulse = false;
    bool n_front = front, n_ready = ready;
    if (swap && ready) n_front = !front;
    if (fdone) n_ready = true; else if (swap && ready) n_ready = false;
    if (swap) { if (ready) c.shown++; else c.swap_empty++; }
    if (trace) {
      if (swap) fprintf(trace, "%llu SWAP %d\n", (unsigned long long)cyc, (int)ready);
      if (fdone) fprintf(trace, "%llu DONE\n", (unsigned long long)cyc);
      if (v->DBG_FRAME_TICK) fprintf(trace, "%llu TICK ready=%d busy=%d\n", (unsigned long long)cyc, (int)ready, (int)v->DBG_TR_BUSY);
      if (nmi_pulse) { fprintf(trace, "%llu NMI\n", (unsigned long long)cyc); nmi_pulse = false; }
    }

    // ---- SMS clock enable ----
    uint32_t sum = ce_acc + SMS_K;
    bool n_ce = (sum >> 25) & 1; uint32_t n_ce_acc = sum & 0x1FFFFFF;

    // ---- stats taken on this edge's inputs ----
    if (ce && !rst) {
      c.ce++;
      uint8_t w = v->DBG_WAIT;
      if (w & 1) c.ce_wait_rom++;
      if (w & 2) c.ce_wait_wram++;
    }

    // ---- posedge with the current registers ----
    uint8_t pad = pad1();
    uint64_t in = (uint64_t)rst | (uint64_t)ce << 1 | (uint64_t)din << 2 | (uint64_t)rom_rdy << 10
                | (uint64_t)wack << 11 | (uint64_t)pad << 12 | (uint64_t)ready << 20 | (uint64_t)!front << 21
                | (uint64_t)swap << 22;
    bool tick_before = v->DBG_FRAME_TICK, busy_before = v->DBG_TR_BUSY;
    bool eval = exact || !frozen || in != frozen_in;
    if (eval) {
      frozen = false;
      v->RST = rst; v->CE = ce; v->ROM_DATA = din; v->ROM_RDY = rom_rdy; v->BUF_WACK = wack;
      v->PAD1 = pad; v->TR_GATE = ready; v->BACK_SET = !front;
#ifdef VSMS_PORT_DBG_SWAP
      v->DBG_SWAP = swap; v->DBG_SWAP_OK = ready;   // the WIP core's swap counters
#endif
      v->DBG_FORCE_TR = 0; v->DBG_FORCE_FULL = 0; v->DBG_VRAM_ADDR = 0; v->DBG_CRAM_ADDR = 0;
      clock_edge();
      if (!exact) {
        if (in == prev_in && snap_ok) { if (snap_same_and_save()) same++; else same = 0; }
        else { snap_same_and_save(); same = 0; }
        snap_ok = true; prev_in = in;
        if (same >= 2) { frozen = true; frozen_in = in; }
      }
    } else c.coasted++;

    // frame pacing: FRAME_TICK is a 1-CLK pulse; the pass starts on the next edge if idle + ungated
    if (tick_before && !rst) {
      c.sms_frames++;
      if (busy_before) c.tr_skip_busy++; else if (ready) c.tr_skip_gate++; else c.tr_started++;
    }
    bool busy_now = v->DBG_TR_BUSY;
    if (busy_now && !tr_busy_prev) { tr_t0 = cyc; tr_bytes = 0; }
    if (!busy_now && tr_busy_prev) {
      uint64_t d = cyc - tr_t0;
      c.tr_done++; c.tr_cycles_sum += d; if (d > c.tr_cycles_max) c.tr_cycles_max = d;
      if (d > frame_tr_max) frame_tr_max = d;
    }
    tr_busy_prev = busy_now;
    if (st == WR_END) { c.tr_bytes++; tr_bytes++; }

    // ---- commit ----
    rd_pend = n_rd_pend; wr_pend = n_wr_pend; ctx_pend = n_ctx_pend; wr_busy = n_wr_busy;
    rom_rdy = n_rom_rdy; wack = n_wack; rd_addr = n_rd_addr; wr_addr = n_wr_addr; wr_data = n_wr_data; din = n_din;
    st = n_st; delay = n_delay; front = n_front; ready = n_ready; ce = n_ce; ce_acc = n_ce_acc;
    cyc++;
  }
};

} // namespace

SmsCore *make_sms_core(uint8_t *psram) {
  if (const char *off = getenv("CICLONE_SMS"))
    if (!strcmp(off, "0")) return nullptr;
  return new SmsVerilated(psram);
}

} // namespace ciclone
