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
