/* Ciclone host diskio - the FatFs block layer over the SD image.
 *
 * Replaces lpc175x/sdnative.c's disk_* (which the firmware FatFs ff.c calls):
 *   disk_initialize / disk_status / disk_read / disk_write / disk_ioctl.
 * Backed by ciclone_sd_* (a 512-byte-sector file image, sd_image.c).
 *
 * CRITICAL - the SD->PSRAM offload (mirrors the hardware fpga_sddma): ff.c sets
 * `sd_offload=1` right before a disk_read that should stream straight into PSRAM
 * instead of the caller buffer (ROM/SRAM loads). When that flag is set we read
 * the sectors from the image and push them to the FpgaModel's PSRAM at the
 * current cursor via ciclone_fpga_dma_write (the cursor was placed by
 * set_mcu_addr -> SPI 0x00 just before). Partial offload (sd_offload_partial)
 * streams only [start,end) of a single sector. See ff.c lines 2595/2644.
 */
#include "config.h"
#include "diskio.h"
#include "../include/ciclone_seam.h"

#include <string.h>
#include <stdio.h>

/* offload control globals (defined in firmware main.c; ff.c drives them) */
extern int sd_offload, ff_sd_offload, sd_offload_tgt;
extern int sd_offload_partial;
extern uint16_t sd_offload_partial_start;
extern uint16_t sd_offload_partial_end;

/* diskio.h API also declares these; firmware defines disk_state in main.c. */
extern volatile enum diskstates disk_state;

#define SECTOR_SIZE 512u

DSTATUS disk_initialize(BYTE pdrv) {
  (void)pdrv;
  disk_state = DISK_OK;
  return ciclone_sd_sectorcount() ? 0 : STA_NOINIT;
}

DSTATUS disk_status(BYTE pdrv) {
  (void)pdrv;
  /* No medium only if the image is empty/unopened. */
  return ciclone_sd_sectorcount() ? 0 : STA_NODISK;
}

void disk_init(void) { disk_state = DISK_OK; }

DRESULT disk_read(BYTE pdrv, BYTE *buff, DWORD sector, UINT count) {
  (void)pdrv;
  if (sd_offload) {
    /* Stream sectors from the image directly into model PSRAM. */
    static uint8_t sec[SECTOR_SIZE];
    /* The partial range covers the FIRST sector of the call only, and is consumed by it
       (lpc175x/sdnative.c read_block clears sd_offload_partial after each block): an
       unaligned f_lseek leaves the flag set, and the whole sectors that follow are full. */
    for (UINT i = 0; i < count; i++) {
      if (ciclone_sd_read(sector + i, sec, 1) != 0) return RES_ERROR;
      uint16_t s = 0, e = SECTOR_SIZE;
      if (sd_offload_partial) {
        s = sd_offload_partial_start & 0x1ff;
        e = sd_offload_partial_end & 0x3ff;
        if (e > SECTOR_SIZE) e = SECTOR_SIZE;
        if (s > e) s = e;
        sd_offload_partial = 0;
      }
      /* target 1 = the MSU-1 DAC buffer (FMV soundtrack, PCM player): not PSRAM */
      if (sd_offload_tgt == 1) ciclone_fpga_dac_write(sec + s, (uint32_t)(e - s));
      else ciclone_fpga_dma_write(sec + s, (uint32_t)(e - s));
    }
    return RES_OK;
  }
  /* Normal path: fill the caller buffer. */
  if (ciclone_sd_read(sector, buff, count) != 0) return RES_ERROR;
  return RES_OK;
}

DRESULT disk_write(BYTE pdrv, const BYTE *buff, DWORD sector, UINT count) {
  (void)pdrv;
  if (ciclone_sd_write(sector, buff, count) != 0) return RES_ERROR;
  return RES_OK;
}

DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff) {
  (void)pdrv;
  switch (cmd) {
    case CTRL_SYNC:
      return RES_OK;
    case GET_SECTOR_COUNT:
      if (buff) *(DWORD *)buff = (DWORD)ciclone_sd_sectorcount();
      return RES_OK;
    case GET_SECTOR_SIZE:
      if (buff) *(WORD *)buff = SECTOR_SIZE;
      return RES_OK;
    case GET_BLOCK_SIZE:
      if (buff) *(DWORD *)buff = 1;   /* erase block size in sectors */
      return RES_OK;
    default:
      return RES_OK;
  }
}
