// CICLONE M3 - diagnóstico VCD da leitura pelo barramento SNES no FPGA Verilado.
// Escreve 0x42 em byte 0x10 via MCU, depois dirige uma leitura SNES de $C0:0010 com
// dump VCD, para inspecionar SNES_READr/IS_ROM/ROM_ADDR0/SNES_DATA e achar por que o
// drive de SNES_DATA não acontece. Saída: build/snes_read.vcd
#include "Vmain.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <cstdio>
#include <cstdint>
#include <vector>

static Vmain *top;
static VerilatedVcdC *tfp;
static uint64_t g_t = 0;
static int g_dump = 0;
double sc_time_stamp() { return (double)g_t; }

static std::vector<uint16_t> psram;
static std::vector<uint8_t>  sram;
static void service_mem() {
  uint32_t ra = top->ROM_ADDR & 0x3FFFFF, raw = top->RAM_ADDR & 0x7FFFF;
  if (!top->ROM_WE) {
    uint16_t cur = psram[ra];
    if (!top->ROM_BLE) cur = (cur & 0xFF00) | (top->ROM_DATA & 0x00FF);
    if (!top->ROM_BHE) cur = (cur & 0x00FF) | (top->ROM_DATA & 0xFF00);
    psram[ra] = cur;
  } else top->ROM_DATA = psram[ra];
  if (!top->RAM_WE) sram[raw] = top->RAM_DATA; else top->RAM_DATA = sram[raw];
}
static int g_cpu = 0, g_bgclk = 1;
static inline void tick() {
  if (g_bgclk && ++g_cpu >= 7) { g_cpu = 0; top->SNES_CPU_CLK_IN = !top->SNES_CPU_CLK_IN; }
  if (g_bgclk) top->SNES_SYSCLK = !top->SNES_SYSCLK;
  top->CLKIN = 0; top->eval(); service_mem(); top->eval(); if (g_dump) tfp->dump(g_t++);
  top->CLKIN = 1; top->eval(); service_mem(); top->eval(); if (g_dump) tfp->dump(g_t++);
}
static void clkn(int n) { for (; n > 0; n--) tick(); }
static uint8_t spi_byte(uint8_t tx) {
  uint8_t rx = 0;
  for (int k = 0; k < 8; k++) {
    top->SPI_MOSI = (tx >> (7 - k)) & 1; top->SPI_SCK = 0; clkn(6);
    rx = (rx << 1) | (top->SPI_MISO & 1); top->SPI_SCK = 1; clkn(6);
  }
  top->SPI_SCK = 0; clkn(6); return rx;
}
static void sel()  { top->SPI_SS = 0; clkn(6); }
static void desel(){ top->SPI_SS = 1; clkn(6); }
static void rdy(int c){ for (int i=0;i<c && !top->MCU_RDY;i++) clkn(1); }

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  Verilated::traceEverOn(true);
  psram.assign(0x400000, 0); sram.assign(0x80000, 0);
  top = new Vmain;
  tfp = new VerilatedVcdC; top->trace(tfp, 99); tfp->open("build/snes_read.vcd");

  top->SPI_SS=1; top->SNES_READ_IN=1; top->SNES_WRITE_IN=1; top->SNES_ROMSEL_IN=1;
  top->SNES_ADDR_IN=0; top->SNES_PARD_IN=1; top->SNES_PAWR_IN=1; top->SD_DAT=0xf;
  clkn(200);
  // mapper 0 + rom_mask + escreve 0x42 em byte 0x10
  sel(); spi_byte(0x30); desel();
  sel(); spi_byte(0x10); spi_byte(0x3f); spi_byte(0xff); spi_byte(0xff); desel();
  sel(); rdy(400); spi_byte(0x00); spi_byte(0x00); spi_byte(0x00); spi_byte(0x10); desel();
  sel(); spi_byte(0x98); spi_byte(0x42); rdy(400); desel();
  clkn(40);
  printf("psram[4]=0x%04x (esperado high=0x42)\n", psram[4]);

  // leitura SNES com dump VCD; clock de fundo ligado p/ free slots
  g_dump = 1;
  top->SNES_ADDR_IN = 0xC00010; top->SNES_ROMSEL_IN = 0; top->SNES_READ_IN = 0;
  clkn(60);
  printf("durante leitura: SNES_DATA=0x%02x DATABUS_OE=%d DIR=%d ROM_ADDR=0x%06x\n",
         top->SNES_DATA, top->SNES_DATABUS_OE, top->SNES_DATABUS_DIR, top->ROM_ADDR & 0x3FFFFF);
  top->SNES_READ_IN = 1; top->SNES_ROMSEL_IN = 1; clkn(20);
  g_dump = 0;
  tfp->close();
  printf("VCD -> build/snes_read.vcd\n");
  top->final(); return 0;
}
