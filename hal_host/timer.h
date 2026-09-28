/* Ciclone host shim for src/lpc175x/timer.h - shadows it via -I order.
 *
 * getticks() must keep ADVANCING so the firmware's deadline loops
 * (while(getticks() < timeout) ...) make progress and time out instead of
 * spinning forever. We back it with a real monotonic clock scaled to the
 * firmware's HZ=100 (1 tick = 10 ms). delay_* are implemented in hal_stubs.c. */
#ifndef CICLONE_HOST_TIMER_H
#define CICLONE_HOST_TIMER_H

/* Claim the real lpc175x/timer.h guard so its in-tree copy expands to nothing. */
#ifndef TIMER_H
#define TIMER_H
#endif

#include <stdint.h>

typedef unsigned int tick_t;

#define HZ 100
#define WARMUP_TICKS 15
#define RITINT 0
#define RITEN  3

#define MS_TO_TICKS(x) ((x) / 10)
#define time_after(a, b)  ((int)(b) - (int)(a) < 0)
#define time_before(a, b) time_after(b, a)

#ifdef __cplusplus
extern "C" {
#endif
tick_t ciclone_host_getticks(void);   /* monotonic, 10 ms per tick */
void   timer_init(void);
void   delay_us(unsigned int time);
void   delay_ms(unsigned int time);
void   sleep_ms(unsigned int time);
#ifdef __cplusplus
}
#endif

static inline tick_t getticks(void) { return ciclone_host_getticks(); }

#endif /* CICLONE_HOST_TIMER_H */
