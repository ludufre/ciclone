// CICLONE M2.5 - FxPakPro ponta-a-ponta sobre um PTY (transporte serial real).
// Abre o PTY (lado device), roda uma bomba (PTY -> servidor FxPak real), e age como
// CLIENTE no lado serial: manda INFO, lê a resposta. É o caminho que o QUsb2snes usa.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <atomic>
#include <pthread.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>

extern "C" { int ciclone_cdc_pty_open(char *slavepath); void ciclone_cdc_pty_pump(void); }

static std::atomic<bool> g_run{true};
static void *pump(void *) { while (g_run) { ciclone_cdc_pty_pump(); usleep(300); } return nullptr; }

int main(void) {
  char slave[128];
  if (ciclone_cdc_pty_open(slave) != 0) { fprintf(stderr, "pty open falhou\n"); return 2; }
  pthread_t th; pthread_create(&th, nullptr, pump, nullptr);
  usleep(50000);

  int cfd = open(slave, O_RDWR | O_NOCTTY);
  if (cfd < 0) { perror("open slave"); g_run = false; pthread_join(th, nullptr); return 2; }
  struct termios t; if (tcgetattr(cfd, &t) == 0) { cfmakeraw(&t); tcsetattr(cfd, TCSANOW, &t); }

  unsigned char cmd[512]; memset(cmd, 0, sizeof(cmd));
  cmd[0]='U'; cmd[1]='S'; cmd[2]='B'; cmd[3]='A'; cmd[4]=11;   // opcode INFO
  if (write(cfd, cmd, sizeof(cmd)) != (ssize_t)sizeof(cmd)) { perror("write cmd"); }

  unsigned char resp[512]; memset(resp, 0, sizeof(resp));
  int got = 0;
  for (int i = 0; i < 400 && got < 320; i++) {
    ssize_t r = read(cfd, resp + got, sizeof(resp) - got);
    if (r > 0) got += (int)r; else usleep(2000);
  }
  g_run = false; pthread_join(th, nullptr); close(cfd);

  printf("recebido %d bytes  magic=%c%c%c%c  opcode=%d  ver@260='%.20s'\n",
         got, resp[0], resp[1], resp[2], resp[3], resp[4], (char *)(resp + 260));
  int ok = got >= 320 && resp[0]=='U' && resp[1]=='S' && resp[2]=='B' && resp[3]=='A'
           && strncmp((char *)resp + 260, "ciclone-host", 12) == 0;
  printf("== %s - FxPakPro sobre PTY: cliente <-> servidor REAL do firmware ==\n", ok ? "PASSOU" : "FALHOU");
  return ok ? 0 : 1;
}
