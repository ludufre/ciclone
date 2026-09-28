/* Ciclone host RTC stubs - separate TU because rtc.h defines its own `struct tm`
 * (uint8_t fields) that collides with libc <time.h>. So this file includes the
 * firmware rtc.h and pulls the host wall-clock via ciclone_host_localtime6()
 * (implemented in hal_stubs.c, which owns <time.h>). RTC always reports OK. */
#include "config.h"
#include "rtc.h"
#include <stdint.h>

void ciclone_host_localtime6(int *y, int *mo, int *d, int *h, int *mi, int *s, int *wday);

rtcstate_t rtc_state = RTC_OK;

void rtc_init(void) {}
uint8_t rtc_isvalid(void) { return RTC_OK; }
void invalidate_rtc(void) {}
void set_rtc(struct tm *t) { (void)t; }
void printtime(struct tm *t) { (void)t; }
void testbattery(void) {}

void read_rtc(struct tm *t) {
  if (!t) return;
  int y, mo, d, h, mi, s, wd;
  ciclone_host_localtime6(&y, &mo, &d, &h, &mi, &s, &wd);
  t->tm_year = (uint16_t)y; t->tm_mon = (uint8_t)(mo - 1); t->tm_mday = (uint8_t)d;
  t->tm_hour = (uint8_t)h; t->tm_min = (uint8_t)mi; t->tm_sec = (uint8_t)s; t->tm_wday = (uint8_t)wd;
}

static uint64_t to_bcd(uint64_t v, int digits) {
  uint64_t r = 0; for (int i = 0; i < digits; i++) { r |= (uint64_t)(v % 10) << (4 * i); v /= 10; } return r;
}
uint64_t get_bcdtime(void) {
  int y, mo, d, h, mi, s, wd;
  ciclone_host_localtime6(&y, &mo, &d, &h, &mi, &s, &wd);
  return (to_bcd((uint64_t)y, 4) << 40) | (to_bcd((uint64_t)mo, 2) << 32)
       | (to_bcd((uint64_t)d, 2) << 24) | (to_bcd((uint64_t)h, 2) << 16)
       | (to_bcd((uint64_t)mi, 2) << 8) | to_bcd((uint64_t)s, 2);
}
void set_bcdtime(uint64_t b) { (void)b; }
void bcdtime2srtctime(uint64_t bcdtime, uint8_t *srtctime) { (void)bcdtime; if (srtctime) for (int i = 0; i < 8; i++) srtctime[i] = 0; }
uint64_t srtctime2bcdtime(uint8_t *srtctime) { (void)srtctime; return 0; }
void time2gtime(struct gtm *g, struct tm *t) { (void)t; if (g) { g->gtm_sec = g->gtm_min = g->gtm_hour = g->gtm_pad = 0; g->gtm_days = 0; } }
uint8_t get_deltagtime(struct gtm *dd, struct gtm *t) { (void)t; if (dd) { dd->gtm_sec = dd->gtm_min = dd->gtm_hour = dd->gtm_pad = 0; dd->gtm_days = 0; } return 0; }
