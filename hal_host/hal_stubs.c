/* Ciclone host HAL stubs - replace the lpc175x/* drivers for the host build.
 *
 * These satisfy the firmware's HAL surface (clock/power/led/timer/uart/rtc/
 * sdnative) without touching any LPC register. SPI (the FpgaModel seam) and the
 * SD image backend live elsewhere (behavioral.cpp / sd_image.c / diskio.c).
 *
 * Compiled with the SAME shadow headers as the firmware (-I hal_host first), so
 * the host config.h / timer.h / spi.h apply here too. */
#include "config.h"
#include "timer.h"
#include "led.h"
#include "power.h"
#include "clock.h"
#include "sdnative.h"
#include "cic.h"

#include <stdlib.h>
#include <string.h>
#include <time.h>     /* host clock; NOTE: do NOT include rtc.h here - its
                         struct tm collides with libc's. RTC lives in rtc_host.c */
#include <stdio.h>
#include <stdint.h>

/* ---- host_lpc.h peripheral storage (the dummy register banks) ----------- */
LPC_GPIO_TypeDef    ciclone_gpio_bank[5];
LPC_SSP_TypeDef     ciclone_ssp0;
LPC_SC_TypeDef      ciclone_sc;
LPC_TIM_TypeDef     ciclone_tim3;
LPC_PWM_TypeDef     ciclone_pwm1;
LPC_PINCON_TypeDef  ciclone_pincon;
LPC_GPDMACH_TypeDef ciclone_gpdmach0;

/* ---- timer ------------------------------------------------------------- */
volatile tick_t ticks;   /* real timer.h had this; some objs may reference it */

static uint64_t mono_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
static uint64_t g_t0_ns;

tick_t ciclone_host_getticks(void) {
  if (!g_t0_ns) g_t0_ns = mono_ns();
  /* HZ=100 -> 10 ms per tick */
  return (tick_t)(((mono_ns() - g_t0_ns) / 1000000ull) / 10ull);
}

void timer_init(void) { g_t0_ns = mono_ns(); }

/* Delays are near-no-ops: we want the smoke test fast, and getticks() is backed
 * by the real clock so deadline-based loops still terminate. A short real sleep
 * keeps any "spin until ticks advance" loop from busy-burning a core. */
static void tiny_sleep(unsigned int us) {
  struct timespec rq = { .tv_sec = us / 1000000u, .tv_nsec = (long)(us % 1000000u) * 1000L };
  nanosleep(&rq, NULL);
}
void delay_us(unsigned int t) { (void)t; }
void delay_ms(unsigned int t) { tiny_sleep(t > 5 ? 200 : 0); }   /* cap to ~0.2ms */
void sleep_ms(unsigned int t) { (void)t; }

/* ---- uart -> host stdio ------------------------------------------------ */
int ciclone_uart_echo = 1;   /* test can silence the firmware's console spam */

void uart_init(void) {}
void uart_putc(char c) { if (ciclone_uart_echo) { fputc((unsigned char)c, stdout); } }
void uart_puts(const char *s) { if (ciclone_uart_echo) fputs(s, stdout); }
void uart_puthex(uint8_t n) { if (ciclone_uart_echo) printf("%02x", n); }
void uart_puts_hex(const char *t) {
  if (!ciclone_uart_echo) return;
  for (const unsigned char *p = (const unsigned char *)t; *p; p++) printf("%02x", *p);
}
void uart_trace(void *ptr, uint32_t start, uint32_t len) { (void)ptr; (void)start; (void)len; }
void uart_flush(void) { fflush(stdout); }
unsigned char uart_getc(void) { return 0; }    /* no console input on the host */
unsigned char uart_gotc(void) { return 0; }    /* never any pending input */

/* ---- power / clock ----------------------------------------------------- */
void power_init(void) {}
void clock_disconnect(void) {}
void clock_init(void) {}
void setFlashAccessTime(uint8_t c) { (void)c; }
void setPLL0MultPrediv(uint16_t m, uint8_t p) { (void)m; (void)p; }
void enablePLL0(void) {}
void disablePLL0(void) {}
void connectPLL0(void) {}
void disconnectPLL0(void) {}
void PLL0feed(void) {}
void setPLL1MultDiv(uint8_t m, uint8_t p) { (void)m; (void)p; }
void enablePLL1(void) {}
void disablePLL1(void) {}
void connectPLL1(void) {}
void disconnectPLL1(void) {}
void PLL1feed(void) {}
void setCCLKDiv(uint8_t d) { (void)d; }
void setUSBCLKDiv(uint8_t d) { (void)d; }
void enableMainOsc(void) {}
void disableMainOsc(void) {}
void setClkSrc(uint8_t s) { (void)s; }

/* ---- led --------------------------------------------------------------- */
void readbright(uint8_t b) { (void)b; }
void writebright(uint8_t b) { (void)b; }
void rdybright(uint8_t b) { (void)b; }
void readled(unsigned int s) { (void)s; }
void writeled(unsigned int s) { (void)s; }
void rdyled(unsigned int s) { (void)s; }
void led_clkout32(uint32_t v) { (void)v; }
void toggle_rdy_led(void) {}
void toggle_read_led(void) {}
void toggle_write_led(void) {}
void led_pwm(void) {}
void led_std(void) {}
void led_init(void) {}
void led_error(void) {}
void led_set_brightness(uint8_t b) { (void)b; }
/* led_panic on the real HW blinks forever (fatal). On the host that would hang
 * the firmware thread; make it abort the run loudly instead so the test reports
 * the panic code rather than wedging. */
void led_panic(uint8_t led_states) {
  fprintf(stderr, "\n[hal_host] led_panic(%u) - firmware hit a fatal HW path\n", led_states);
  fflush(stderr);
  abort();
}

/* ---- host broken-down time helper (used by rtc_host.c, which can't include
 * <time.h> because its struct tm collides with the firmware's rtc.h one) ---- */
/* CICLONE_FIXED_TIME="YYYY-MM-DD HH:MM:SS" congela o relógio (testes do menu precisam de
 * tela determinística: a barra de status mostra a hora). Sem ela, é o relógio do host. */
static int host_now(struct tm *lt) {
  const char *f = getenv("CICLONE_FIXED_TIME");
  memset(lt, 0, sizeof *lt);
  if (f && sscanf(f, "%d-%d-%d %d:%d:%d", &lt->tm_year, &lt->tm_mon, &lt->tm_mday,
                  &lt->tm_hour, &lt->tm_min, &lt->tm_sec) == 6) {
    lt->tm_year -= 1900; lt->tm_mon -= 1; lt->tm_isdst = -1;
    time_t t = mktime(lt);            /* normaliza e calcula o dia da semana */
    localtime_r(&t, lt);
    return 1;
  }
  time_t now = time(NULL);
  localtime_r(&now, lt);
  return 0;
}

void ciclone_host_localtime6(int *y, int *mo, int *d, int *h, int *mi, int *s, int *wday) {
  struct tm lt; host_now(&lt);
  if (y) *y = lt.tm_year + 1900;
  if (mo) *mo = lt.tm_mon + 1;
  if (d) *d = lt.tm_mday;
  if (h) *h = lt.tm_hour;
  if (mi) *mi = lt.tm_min;
  if (s) *s = lt.tm_sec;
  if (wday) *wday = (lt.tm_wday + 6) % 7;   /* firmware: Sunday=6 */
}

/* ---- sdnative: native SD driver is replaced by diskio.c over the image --- */
void sdn_init(void) {}
void sdn_changed(void) {}
uint8_t *sdn_getcid(void) { static uint8_t cid[16] = {0}; return cid; }
void sdn_gettacc(uint32_t *tacc_max, uint32_t *tacc_avg) { if (tacc_max) *tacc_max = 0; if (tacc_avg) *tacc_avg = 0; }

/* ---- CMSIS intrinsic used once (NVIC_SystemReset in some paths) ---------- */
void NVIC_SystemReset(void) { fprintf(stderr, "[hal_host] NVIC_SystemReset() ignored\n"); }

/* ---- FatFs timestamp hook (real impl lives in lpc175x/rtc.c, not built) -- */
uint32_t get_fattime(void) {
  struct tm lt; host_now(&lt);
  return ((uint32_t)(lt.tm_year - 80) << 25) | ((uint32_t)(lt.tm_mon + 1) << 21)
       | ((uint32_t)lt.tm_mday << 16) | ((uint32_t)lt.tm_hour << 11)
       | ((uint32_t)lt.tm_min << 5) | ((uint32_t)(lt.tm_sec / 2));
}

/* uart console echo toggle (declared above) accessor for C++ test harness. */
void ciclone_set_uart_echo(int on) { ciclone_uart_echo = on; }
