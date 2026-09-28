/* Ciclone host shim for src/lpc175x/uart.h - shadows it via -I order.
 *
 * The real uart.h re-declares printf/snprintf with non-libc prototypes (it ships
 * its own printf.c). On the host we use libc's stdio printf/snprintf instead
 * (printf.c is NOT compiled), so here we declare ONLY the uart_* surface and
 * pull printf/snprintf from <stdio.h>. uart_putc etc. are defined in
 * hal_stubs.c (route to stdout). */
#ifndef CICLONE_HOST_UART_H
#define CICLONE_HOST_UART_H

/* Claim the real lpc175x/uart.h guard so its in-tree copy expands to nothing
 * (its printf/snprintf re-declarations clash with libc on the host). */
#ifndef UART_H
#define UART_H
#endif

#include <stdio.h>
#include <stdint.h>

#define uart_puts_P(str) uart_puts(str)
#define uart_putcrlf()   uart_putc('\n')

void uart_init(void);
unsigned char uart_getc(void);
unsigned char uart_gotc(void);
void uart_putc(char c);
void uart_puts(const char *str);
void uart_puthex(uint8_t num);
void uart_puts_hex(const char *text);
void uart_trace(void *ptr, uint32_t start, uint32_t len);
void uart_flush(void);

#endif /* CICLONE_HOST_UART_H */
