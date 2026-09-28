/* Ciclone host replacement for src/fpga.c.
 *
 * The real fpga.c bit-bangs the Xilinx serial-configuration interface over GPIO
 * (PROG_B/INIT_B/DONE/CCLK/DIN) to load a bitstream from SD/cfgware. None of
 * that is meaningful on the host: the FPGA *is* the behavioral model, and "load
 * a bitstream" maps to "reconfigure the model" (which resets the SNESCMD BRAM,
 * exactly like the hardware does on reconfig - see behavioral.cpp::reconfigure).
 *
 * So fpga_pgm()/fpga_rompgm() route to ciclone_fpga_reconfigure() and set the
 * fpga_config marker the menu boot logic checks; the GPIO/DONE-poll machinery is
 * dropped. Everything else in the firmware (fpga_spi.c and its set_mcu_addr /
 * sram_* callers) is the REAL code and drives the model through the SPI seam.
 *
 * This is the one file where keeping extern/src/fpga.c verbatim was impossible
 * on the host; it is replaced here rather than edited in place.
 */
#include "config.h"
#include "fpga.h"
#include "fpga_spi.h"
#include "uart.h"
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif
void ciclone_fpga_reconfigure(const char *core);   /* glue -> model->reconfigure */
#ifdef __cplusplus
}
#endif

uint8_t SPI_OFFLOAD;
const uint8_t *fpga_config;
uint8_t fpga_boot_led = 0;

void fpga_set_prog_b(uint8_t val) { (void)val; }
void fpga_set_cclk(uint8_t val) { (void)val; }
int  fpga_get_initb(void) { return 1; }    /* always responsive on the host */
int  fpga_get_done(void) { return 1; }     /* config "completes" instantly */

void fpga_init(void) { SPI_OFFLOAD = 0; }
void fpga_postinit(void) {}

void fpga_pgm(uint8_t *filename) {
  /* "Program" the model: reconfigure (resets SNESCMD), then mark which core is
     loaded so the menu's `fpga_config != FPGA_BASE` / `== FPGA_ROM` checks work. */
  printf("[fpga_host] fpga_pgm(%s) -> model reconfigure\n",
         filename ? (const char *)filename : "(null)");
  ciclone_fpga_reconfigure(filename ? (const char *)filename : "");
  fpga_config = filename;
  fpga_boot_led = 0;
  fpga_postinit();
}

void fpga_rompgm(void) {
  printf("[fpga_host] fpga_rompgm() -> model reconfigure (boot display)\n");
  ciclone_fpga_reconfigure("rom");
  fpga_config = FPGA_ROM;
  fpga_postinit();
}
