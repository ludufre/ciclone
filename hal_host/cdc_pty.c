/* CICLONE M2.5 - transporte FxPakPro do firmware sobre um PTY do host.
 *
 * O servidor FxPakPro REAL (src/usbinterface.c, na libsd2snesfw) fala por uma porta
 * serial (CDC-ACM). Aqui expomos um PTY: o lado MESTRE é a "porta USB" do device (o
 * firmware lê/escreve por ele via CDC_block_send + a bomba abaixo); o lado ESCRAVO é a
 * porta serial que o QUsb2snes / usb2snes abre. Sem emular USB de verdade.
 *
 * Uso: ciclone_cdc_pty_open(slavepath) abre o PTY e marca "conectado"; chame
 * ciclone_cdc_pty_pump() no loop (lê o PTY -> usbint_recv_flit -> usbint_handler).
 */
#include <stdint.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <termios.h>
#include <sys/ioctl.h>
/* openpty lives in macOS <util.h>, but the firmware's own src/util.h shadows it on the
   -I path (the strutil helpers) -- declare it directly instead. */
int openpty(int *amaster, int *aslave, char *name, struct termios *termp, struct winsize *winp);

extern void usbint_recv_flit(const unsigned char *in, int length);
extern int  usbint_handler(void);
extern void usbint_set_state(unsigned open);

static int g_master = -1;

/* Abre o PTY; preenche slavepath (>=128B) com o caminho da porta serial p/ o cliente. */
int ciclone_cdc_pty_open(char *slavepath) {
  int slave;
  char name[128];
  struct termios tio; memset(&tio, 0, sizeof(tio)); cfmakeraw(&tio);   // binário: sem line-discipline
  if (openpty(&g_master, &slave, name, &tio, NULL) != 0) { perror("openpty"); return -1; }
  fcntl(g_master, F_SETFL, O_NONBLOCK);
  if (slavepath) { strncpy(slavepath, name, 127); slavepath[127] = 0; }
  printf("[cdc_pty] FxPakPro serial: %s\n", name);
  usbint_set_state(1);   /* "conectado" */
  return 0;
}

/* CDC do device -> host: o firmware escreve a resposta no mestre (cliente lê no escravo). */
uint32_t CDC_block_send(uint8_t *buffer, uint32_t send_size) {
  if (g_master < 0) return send_size;
  ssize_t off = 0;
  while (off < (ssize_t)send_size) {
    ssize_t w = write(g_master, buffer + off, send_size - off);
    if (w > 0) off += w;
    else break;
  }
  return send_size;
}
void CDC_block_init(uint8_t *buffer, uint32_t send_size) { memset(buffer, 0, send_size); }

/* Bomba: lê o que o cliente mandou (host -> device) e entrega ao servidor FxPak. */
void ciclone_cdc_pty_pump(void) {
  unsigned char buf[512];
  ssize_t r = read(g_master, buf, sizeof(buf));
  if (r > 0) usbint_recv_flit(buf, (int)r);
  usbint_handler();
}
