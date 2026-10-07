/* Ciclone host SD backend - a raw disk image file as 512-byte sectors.
 * Implements the ciclone_sd_* half of include/ciclone_seam.h. Lastingly mounted
 * by ciclone_sd_open(path); used by diskio.c (FatFs) and the SD->PSRAM offload. */
#include "../include/ciclone_seam.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#define SECTOR_SIZE 512u

static FILE    *g_img;
static uint32_t g_sectors;

/* Read statistics, for tests that measure how much card traffic a menu action costs.
   A restart is what lpc175x/sdnative.c read_block pays when a sector is NOT the one right
   after the previous read (stop + a new multi-block read command + the card's access time);
   a sequential sector just streams. A write ends the read stream, as it does there. */
static uint64_t g_rd_sectors, g_rd_restarts;
static uint32_t g_rd_last;
static int      g_rd_streaming;

void ciclone_sd_stats(uint64_t *sectors, uint64_t *restarts) {
  *sectors = g_rd_sectors;
  *restarts = g_rd_restarts;
}

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
  /* CICLONE_SD_TRACE=<file>: one line per read, "lba count" */
  static FILE *trace;
  static int trace_init;
  if (!trace_init) {
    trace_init = 1;
    const char *t = getenv("CICLONE_SD_TRACE");
    if (t && *t) trace = fopen(t, "w");
  }
  if (trace) { fprintf(trace, "%u %u\n", lba, count); fflush(trace); }
  for (uint32_t i = 0; i < count; i++) {
    if (!g_rd_streaming || lba + i != g_rd_last + 1) g_rd_restarts++;
    g_rd_last = lba + i;
    g_rd_streaming = 1;
  }
  g_rd_sectors += count;
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
  g_rd_streaming = 0;
  if (fseek(g_img, (long)lba * SECTOR_SIZE, SEEK_SET) != 0) return 1;
  size_t want = (size_t)count * SECTOR_SIZE;
  size_t put = fwrite(buf, 1, want, g_img);
  fflush(g_img);
  return (put == want) ? 0 : 1;
}
