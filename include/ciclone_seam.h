/* Ciclone - contrato (ABI C) entre o firmware do MCU (rodando no host) e o
 * runtime do host (FpgaModel + SD image). É o "seam #1" do projeto.
 *
 * - O firmware chama ciclone_spi_* (via os shims de HAL que sombreiam spi.h/config.h)
 *   e ciclone_sd_* (via o shim de diskio). Byte-stream + framing de chip-select
 *   exatamente como no fio real.
 * - O FpgaModel (C++) IMPLEMENTA ciclone_spi_xxx e ciclone_fpga_dma_write, e CONSOME
 *   ciclone_sd_xxx para o offload SD->PSRAM.
 */
#ifndef CICLONE_SEAM_H
#define CICLONE_SEAM_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* ---- Transporte SPI (MCU -> FPGA) ----------------------------------------
 * Mapeamento dos macros do firmware (fpga_spi.h):
 *   FPGA_SELECT()   -> ciclone_spi_select()
 *   FPGA_DESELECT() -> ciclone_spi_deselect()
 *   FPGA_TX_BYTE(x) -> ciclone_spi_txrx(x)   (rx ignorado)
 *   FPGA_RX_BYTE()  -> ciclone_spi_txrx(0xff)
 *   FPGA_WAIT_RDY() -> (poll) ciclone_spi_mcu_rdy() */
void    ciclone_spi_select(void);
void    ciclone_spi_deselect(void);
uint8_t ciclone_spi_txrx(uint8_t tx);
int     ciclone_spi_mcu_rdy(void);     /* linha FPGA_MCU_RDY: 1=pronto */

/* Offload SD->PSRAM: escreve `len` bytes na PSRAM do modelo no cursor atual
 * (setado por set_mcu_addr via SPI 0x00) e avança o cursor. Chamado pelo shim
 * de diskio quando ff_sd_offload está ativo (espelha o fpga_sddma do hardware). */
void    ciclone_fpga_dma_write(const uint8_t *buf, uint32_t len);
/* O mesmo offload com alvo dac_buf (sd_offload_tgt = 1): o buffer de 2 KB do DAC do
 * MSU-1, no ponteiro de escrita que set_dac_addr posicionou. */
void    ciclone_fpga_dac_write(const uint8_t *buf, uint32_t len);

/* ---- Lado SNES (chip sd2snes do bsnes -> runtime do host) -----------------
 * O chip do bsnes chama estes hooks C; o host_runner os implementa (forte),
 * encaminhando ao FpgaModel ativo. Há defaults FRACOS (weak) no próprio chip
 * para o libsnes/GUI linkarem sem o runtime (chip inativo => open bus). */
int     ciclone_chip_active(void);                 /* 1 = modelo sd2snes ativo */
uint8_t ciclone_chip_snes_read(uint32_t addr);     /* addr 24 bits */
void    ciclone_chip_snes_write(uint32_t addr, uint8_t data);

/* ---- SD card (imagem do host) --------------------------------------------
 * Lastreia tanto o FatFs do firmware (diskio) quanto o offload. Setor = 512 B. */
int      ciclone_sd_read(uint32_t lba, uint8_t *buf, uint32_t count);   /* 0=ok */
int      ciclone_sd_write(uint32_t lba, const uint8_t *buf, uint32_t count);
uint32_t ciclone_sd_sectorcount(void);
int      ciclone_sd_open(const char *path);  /* monta a imagem; 0=ok */

#ifdef __cplusplus
}
#endif
#endif
