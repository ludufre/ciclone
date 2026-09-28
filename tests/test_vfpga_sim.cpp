// CICLONE M3 - FPGA Verilado com memória PSRAM/SRAM EM VERILOG (sim_top.v).
// Como o barramento de memória resolve combinacionalmente dentro da Verilação, o drive
// de SNES_DATA na leitura do barramento SNES deve funcionar. Testa: MCU escreve 0x42 em
// byte 0x10 (via SPI/RTL real) -> SNES lê $C0:0010 (HiROM) e recebe 0x42.
#include "Vsim_top.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
double sc_time_stamp() { return 0; }

static Vsim_top *top;
static int g_cpu = 0;
static inline void clk(int n) {   // CLK2 + clock de fundo do SNES (free slots p/ o MCU)
  for (; n > 0; n--) {
    if (++g_cpu >= 7) { g_cpu = 0; top->SNES_CPU_CLK_IN = !top->SNES_CPU_CLK_IN; }
    top->SNES_SYSCLK = !top->SNES_SYSCLK;
    top->CLKIN = 0; top->eval();
    top->CLKIN = 1; top->eval();
  }
}
static uint8_t spi_byte(uint8_t tx) {
  uint8_t rx = 0;
  for (int k = 0; k < 8; k++) {
    top->SPI_MOSI = (tx >> (7 - k)) & 1; top->SPI_SCK = 0; clk(6);
    rx = (rx << 1) | (top->SPI_MISO & 1); top->SPI_SCK = 1; clk(6);
  }
  top->SPI_SCK = 0; clk(6); return rx;
}
static void sel()  { top->SPI_SS = 0; clk(6); }
static void desel(){ top->SPI_SS = 1; clk(6); }
static void rdy(int c){ for (int i=0;i<c && !top->MCU_RDY;i++) clk(1); }

static int fails = 0;
#define CHECK(c,m) do{ if(!(c)){printf("FAIL: %s\n",m);fails++;} else printf("ok:   %s\n",m);}while(0)

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  top = new Vsim_top;
  top->SPI_SS=1; top->SNES_READ_IN=1; top->SNES_WRITE_IN=1; top->SNES_ROMSEL_IN=1;
  top->SNES_ADDR_IN=0; top->SNES_PARD_IN=1; top->SNES_PAWR_IN=1; top->SD_DAT=0xf;
  clk(200);

  // FPGA vivo?
  sel(); spi_byte(0xf0); uint8_t tok = spi_byte(0xff); desel();
  CHECK(tok == 0xa5, "sim_top: FPGA Verilado responde TEST 0xa5");

  // mapper 0 (HiROM) + rom_mask + escreve 0x42 em byte 0x10 (via RTL -> PSRAM interna)
  sel(); spi_byte(0x30); desel();
  sel(); spi_byte(0x10); spi_byte(0x3f); spi_byte(0xff); spi_byte(0xff); desel();
  sel(); rdy(400); spi_byte(0x00); spi_byte(0x00); spi_byte(0x00); spi_byte(0x10); desel();
  sel(); spi_byte(0x98); spi_byte(0x42); rdy(400); desel();
  clk(40);

  // confirma via leitura do MCU (0x88) que a PSRAM interna recebeu o dado
  sel(); rdy(400); spi_byte(0x00); spi_byte(0x00); spi_byte(0x00); spi_byte(0x10); desel();
  sel(); spi_byte(0x88); rdy(400); uint8_t mcu_rb = spi_byte(0xff); desel();
  printf("MCU readback byte 0x10 = 0x%02x\n", mcu_rb);
  CHECK(mcu_rb == 0x42, "sim_top: round-trip MCU write/read na PSRAM interna");

  // LEITURA PELO BARRAMENTO SNES: $C0:0010 (HiROM byte 0x10). Memória interna =>
  // ROM_DATA combinacional => SNES_DATA deve ser dirigido na janela do ciclo.
  top->SNES_ADDR_IN = 0xC00010; top->SNES_ROMSEL_IN = 0; top->SNES_READ_IN = 0;
  uint8_t snval = 0;
  for (int i = 0; i < 120; i++) { clk(1); uint8_t d = top->SNES_DATA; if (d) snval = d; }
  top->SNES_READ_IN = 1; top->SNES_ROMSEL_IN = 1; clk(20);
  printf("SNES read $C0:0010 = 0x%02x (escrito 0x42)\n", snval);
  CHECK(snval == 0x42, "sim_top: LEITURA pelo barramento SNES do FPGA Verilado (lado-SNES)");

  printf("\n== %s (%d falhas) ==\n", fails ? "FALHOU" : "PASSOU", fails);
  top->final(); return fails ? 1 : 0;
}
