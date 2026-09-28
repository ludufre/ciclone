/* Ciclone host shim for src/bits.h - shadows it via -I order.
 *
 * On the Cortex-M3 BITBAND maps a peripheral bit to its bit-band alias address.
 * On the host there is no such region: every pin reads as 1 (the live firmware
 * paths only WAIT for lines to go high - CIC status, FPGA_WAIT_RDY), and writes
 * go to a discarded scratch cell. The one bit the firmware must act on (FPGA
 * chip select) is handled by SET_BIT/CLEAR_BIT in config.h, not here. */
#ifndef CICLONE_HOST_BITS_H
#define CICLONE_HOST_BITS_H

/* Claim the real src/bits.h guard so its in-tree copy (pulled by headers that
 * sit in src/) expands to nothing and this shadow wins. */
#ifndef _ARM_BITS_H
#define _ARM_BITS_H
#endif

#define BV(x) (1u << (x))

static inline volatile unsigned long *ciclone_bitband_cell(void) {
  static volatile unsigned long cell;
  cell = 1UL;
  return &cell;
}
#define BITBAND(addr, bit)              (*ciclone_bitband_cell())
#define BITBAND_OFF(addr, offset, bit)  (*ciclone_bitband_cell())

#endif /* CICLONE_HOST_BITS_H */
