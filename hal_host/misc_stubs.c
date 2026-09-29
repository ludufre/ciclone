/* Ciclone host misc stubs.
 *
 * cli.c (interactive serial CLI) and ymodem.c (firmware-update-over-serial) are
 * not on the menu+load path and clash with host libc (cli.c defines its own
 * getline). The only CLI symbol the core path calls is cli_entrycheck(), which
 * on hardware just polls the UART for a break char - a no-op on the host (no
 * console input). Stub the small CLI surface here instead of compiling cli.c. */
#include "config.h"

void cli_entrycheck(void) {}   /* no serial console on the host */
void cli_init(void) {}
void cli_loop(void) {}

/* SNES reset line (GPIO_DIR on SNES_RESET_REG/BIT, see config.h). The runner reads
   both flags between frames: while held the CPU does not run, and the release is a
   reset of the emulated console -- that is what a menu reload looks like to it. */
volatile int ciclone_snes_in_reset;
volatile int ciclone_snes_reset_edge;
void ciclone_snes_reset_line(int state) {
  if (state) {
    ciclone_snes_in_reset = 1;
  } else if (ciclone_snes_in_reset) {
    ciclone_snes_in_reset = 0;
    ciclone_snes_reset_edge = 1;
  }
}
