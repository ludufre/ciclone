// CICLONE M2.5 - exercita o servidor FxPakPro REAL (src/usbinterface.c) no host.
// Sem USB/PTY ainda: alimenta um comando INFO direto via usbint_recv_flit (como o
// CDC_BulkOut faria) e captura a resposta via CDC_block_send. Prova que o protocolo
// FxPakPro do firmware roda no PC. O transporte por PTY (cdc_pty.c) é a casca seguinte.
#include <cstdio>
#include <cstdint>
#include <cstring>

extern "C" {
  void usbint_set_state(unsigned open);
  void usbint_recv_flit(const unsigned char *in, int length);
  int  usbint_handler(void);
}

// captura da resposta (CDC do device -> host)
static unsigned char g_resp[512];
static int g_got = 0;
extern "C" {
  uint32_t CDC_block_send(uint8_t *b, uint32_t n) { memcpy(g_resp, b, n < 512 ? n : 512); g_got = 1; return n; }
  void     CDC_block_init(uint8_t *b, uint32_t n) { memset(b, 0, n); }
}

int main(void) {
  usbint_set_state(1);                       // "conectado"
  unsigned char cmd[512]; memset(cmd, 0, sizeof(cmd));
  cmd[0] = 'U'; cmd[1] = 'S'; cmd[2] = 'B'; cmd[3] = 'A';
  cmd[4] = 11;                               // USBINT_SERVER_OPCODE_INFO (GET=0..RESPONSE=15)
  usbint_recv_flit(cmd, 512);                // entrega o comando (como o CDC_BulkOut)
  for (int i = 0; i < 16 && !g_got; i++) usbint_handler();

  printf("resp got=%d  magic=%c%c%c%c  opcode=%d\n", g_got, g_resp[0], g_resp[1], g_resp[2], g_resp[3], g_resp[4]);
  printf("version@260='%.32s'\n", (char *)(g_resp + 260));
  int ok = g_got && g_resp[0] == 'U' && g_resp[1] == 'S' && g_resp[2] == 'B' && g_resp[3] == 'A'
           && strncmp((char *)g_resp + 260, "ciclone-host", 12) == 0;
  printf("== %s - servidor FxPakPro real respondeu INFO no host ==\n", ok ? "PASSOU" : "FALHOU");
  return ok ? 0 : 1;
}
