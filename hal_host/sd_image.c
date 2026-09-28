/* Ciclone host SD backend - a raw disk image file as 512-byte sectors.
 * Implements the ciclone_sd_* half of include/ciclone_seam.h. Lastingly mounted
 * by ciclone_sd_open(path); used by diskio.c (FatFs) and the SD->PSRAM offload. */
#include "../include/ciclone_seam.h"

#include <stdio.h>
#include <stdint.h>

#define SECTOR_SIZE 512u

static FILE    *g_img;
static uint32_t g_sectors;

int ciclone_sd_open(const char *path) {
  if (g_img) { fclose(g_img); g_img = NULL; g_sectors = 0; }
  g_img = fopen(path, "r+b");
  if (!g_img) { fprintf(stderr, "[sd_image] cannot open %s\n", path); return 1; }
  if (fseek(g_img, 0, SEEK_END) != 0) { fclose(g_img); g_img = NULL; return 1; }
  long sz = ftell(g_img);
  if (sz < 0) { fclose(g_img); g_img = NULL; return 1; }
  g_sectors = (uint32_t)(sz / SECTOR_SIZE);
  rewind(g_img);
  fprintf(stderr, "[sd_image] mounted %s (%u sectors, %ld bytes)\n", path, g_sectors, sz);
  return 0;
}

uint32_t ciclone_sd_sectorcount(void) { return g_sectors; }

int ciclone_sd_read(uint32_t lba, uint8_t *buf, uint32_t count) {
  if (!g_img) return 1;
  if (fseek(g_img, (long)lba * SECTOR_SIZE, SEEK_SET) != 0) return 1;
  size_t want = (size_t)count * SECTOR_SIZE;
  size_t got = fread(buf, 1, want, g_img);
  if (got != want) {
    /* Reads past EOF: zero-fill the tail (a sparse/short image is fine). */
    for (size_t i = got; i < want; i++) buf[i] = 0;
  }
  return 0;
}

int ciclone_sd_write(uint32_t lba, const uint8_t *buf, uint32_t count) {
  if (!g_img) return 1;
  if (fseek(g_img, (long)lba * SECTOR_SIZE, SEEK_SET) != 0) return 1;
  size_t want = (size_t)count * SECTOR_SIZE;
  size_t put = fwrite(buf, 1, want, g_img);
  fflush(g_img);
  return (put == want) ? 0 : 1;
}
