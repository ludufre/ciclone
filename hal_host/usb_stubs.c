/* Ciclone host USB stubs.
 *
 * The whole USB/CDC stack (usbdesc/usbcore/usbuser/cdcuser/usbinterface +
 * lpc175x/usbhw) is out of scope for M2 (FxPakPro-over-socket is M2.5). The
 * firmware only *calls* six USB symbols on the menu+load path; stub them so the
 * library links and the menu loop runs with USB simply absent:
 *   USB_Init / CDC_Init / USB_Connect   (boot)
 *   usbint_handler / _server_reset / _server_busy   (menu + game loops)
 *
 * The real headers (usbhw.h/cdcuser.h/usbinterface.h) are still included by the
 * firmware for the declarations; we only provide definitions. */
#include "config.h"
#include <stdint.h>

#include <ctype.h>
void USB_Init(void) {}
void USB_Connect(uint32_t con) { (void)con; }
void CDC_Init(char portNum) { (void)portNum; }

/* M2.5: usbint_handler/_server_reset/_server_busy agora vêm do usbinterface.c REAL
 * (incluído no build). Aqui ficam só os símbolos de HW USB/CMSIS que ele referencia
 * mas não exercita no host. */
void USB_EnableIRQ(void) {}
void USB_DisableIRQ(void) {}
char *strlwr(char *s) { for (char *p = s; *p; ++p) *p = (char)tolower((unsigned char)*p); return s; }
