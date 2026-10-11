// Ciclone - the Verilated SMS core alone, no SNES: loads a .sms at PSRAM 0x300000 and runs N
// seconds of SNES time against a synthetic player (each frame at line 225: a DMA-like burst of
// ROM_HIT cycles reading $E0 with the VRAM writes ctx.v mirrors, the pad, the $EF0005 swap).
// Prints the core's counters, a hash of the translated buffers and the speed of the model.
// Deterministic: CICLONE_SMS_EXACT=1 (every cycle evaluated) must print the same counters and
// hash as the default fast-forward -- that is the check that coasting is exact.
//   build/sms_bench <rom.sms> [seconds] [dma-bytes-per-frame]
// Build (after tools/sms_objs.sh):
//   V="$(verilator --getenv VERILATOR_ROOT)/include"; clang++ -std=gnu++17 -O2 -Wno-invalid-offsetof \
//     -I fpga_model -I build/vsms -I "$V" -I "$V/vltstd" tests/sms_bench.cpp fpga_model/sms_model.cpp \
//     build/vsms/Vsms_core__ALL.a build/vsms/libverilated.a -o build/sms_bench
//   build/sms_bench GAME.sms 6 > a.txt; CICLONE_SMS_EXACT=1 build/sms_bench GAME.sms 6 > b.txt; cmp a.txt b.txt
#include "sms_model.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <ctime>
using namespace ciclone;
int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "uso: %s rom.sms [segundos] [bytes-de-dma]\n", argv[0]); return 2; }
  std::vector<uint8_t> ps(0x1000000, 0);
  FILE *f = fopen(argv[1], "rb"); if (!f) return 2;
  size_t n = fread(&ps[0x300000], 1, 0x100000, f); fclose(f);
  double secs = argc > 2 ? atof(argv[2]) : 2.0;
  int dma = argc > 3 ? atoi(argv[3]) : 2048;
  SmsCore *s = make_sms_core(ps.data());
  if (!s) return 3;
  s->power_on();
  const uint64_t F = 1364 * 262, NMI = 1364 * 225;
  struct timespec a, b; clock_gettime(CLOCK_MONOTONIC, &a);
  uint64_t frames = (uint64_t)(secs * 60.0988);
  s->run_to(0);
  uint32_t lfsr = 1;
  for (uint64_t k = 0; k < frames; k++) {
    uint64_t t = k * F + NMI;
    s->nmi(t);
    for (int i = 0; i < dma; i++) { t += 8; s->cart_cycle(t); s->buf_read(0xE00000 + i); s->ctx_write(t); }
    lfsr = lfsr * 1103515245 + 12345;
    uint8_t pad = (k / 120) & 1 ? 0x80 : 0x00;           // B on/off every 2 s: starts the game
    s->run_to(t); s->ctl_write(0xEF0000, 0); s->ctl_write(0xEF0001, pad);
    s->run_to(t + 40); s->ctl_write(0xEF0005, 0);
    s->screen_on(t + 60);
    s->snes_frame((k + 1) * F);
  }
  clock_gettime(CLOCK_MONOTONIC, &b);
  double wall = (b.tv_sec - a.tv_sec) + (b.tv_nsec - a.tv_nsec) * 1e-9;
  uint64_t h = 1469598103934665603ull;
  for (uint32_t i = 0x380000; i < 0x3A0000; i++) { h ^= ps[i]; h *= 1099511628211ull; }
  char buf[2048]; s->stats(buf, sizeof buf);
  // the speed line goes to stderr: stdout is what EXACT and fast-forward must agree on
  fprintf(stderr, "rom=%zu bytes, %.1f s SNES em %.2f s (%.2fx tempo real)\n", n, secs, wall, secs / wall);
  char *co = strstr(buf, " clk2=");
  if (co) fprintf(stderr, "%s\n", co + 1);                      // coasting is the one thing that differs
  if (co) *co = 0;
  printf("%s\nhash=%016llx\n", buf, (unsigned long long)h);
  return 0;
}
