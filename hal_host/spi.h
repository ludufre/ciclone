/* Ciclone host shim for src/lpc175x/spi.h - shadows it via -I order.
 *
 * fpga_spi.h maps FPGA_TX_BYTE/RX_BYTE/TXRX_BYTE/TX_BLOCK/RX_BLOCK/TX_SYNC onto
 * these spi_* functions. Here they route to the SPI seam (ciclone_spi_txrx),
 * so the REAL fpga_spi.c compiles unmodified and its byte stream reaches the
 * FpgaModel exactly as on the wire. Chip-select framing is done by FPGA_SELECT/
 * DESELECT (config.h) -> ciclone_spi_select/deselect. */
#ifndef CICLONE_HOST_SPI_H
#define CICLONE_HOST_SPI_H

/* Claim the real lpc175x/spi.h guard so its in-tree copy expands to nothing. */
#ifndef SPI_H
#define SPI_H
#endif

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
uint8_t ciclone_spi_txrx(uint8_t tx);
#ifdef __cplusplus
}
#endif

/* Bit positions of the SSP status register (unused on host: FPGA_WAIT_RDY reads
 * them via BITBAND, which is constant 1). Kept for source compatibility. */
#define SPI_TFE 0
#define SPI_TNF 1
#define SPI_RNE 2
#define SPI_RFF 3
#define SPI_BSY 4

typedef enum { SPI_SPEED_FAST, SPI_SPEED_SLOW, SPI_SPEED_FPGA_FAST, SPI_SPEED_FPGA_SLOW } spi_speed_t;

static inline void    spi_preinit(void) {}
static inline void    spi_init(void) {}
static inline void    spi_tx_sync(void) {}
static inline void    spi_tx_byte(uint8_t data) { (void)ciclone_spi_txrx(data); }
static inline uint8_t spi_txrx_byte(uint8_t data) { return ciclone_spi_txrx(data); }
static inline uint8_t spi_rx_byte(void) { return ciclone_spi_txrx(0xff); }
static inline void    spi_tx_block(const void *data, unsigned int length) {
  const uint8_t *p = (const uint8_t *)data;
  for (unsigned int i = 0; i < length; i++) (void)ciclone_spi_txrx(p[i]);
}
static inline void    spi_rx_block(void *data, unsigned int length) {
  uint8_t *p = (uint8_t *)data;
  for (unsigned int i = 0; i < length; i++) p[i] = ciclone_spi_txrx(0xff);
}

#endif /* CICLONE_HOST_SPI_H */
