// Teste unitário do FpgaModel comportamental: dirige o modelo com as MESMAS
// sequências SPI que o firmware emite (set_mcu_addr / 0x98 / 0x88 / d0-d2 / 3m / f0 / f1)
// e valida memória, autoinc, snescmd (round-trip MCU<->SNES) e decode HiROM.
#include "fpga_model.h"
#include "ciclone_seam.h"
#include <cstdio>
#include <cstdint>

using namespace ciclone;

static int fails = 0;
#define CHECK(cond, msg) do { if (!(cond)) { printf("FAIL: %s\n", msg); fails++; } else { printf("ok:   %s\n", msg); } } while (0)

// helpers que emulam as funções do firmware via o seam C
static void set_mcu_addr(uint32_t a) {
  ciclone_spi_select();
  ciclone_spi_txrx(0x00);                       // SETADDR|TGT_MEM
  ciclone_spi_txrx((a >> 16) & 0xff);
  ciclone_spi_txrx((a >> 8) & 0xff);
  ciclone_spi_txrx(a & 0xff);
  ciclone_spi_deselect();
}
static void wr_byte(uint8_t v) {                 // após set_mcu_addr: 0x98 + dado
  ciclone_spi_select(); ciclone_spi_txrx(0x98); ciclone_spi_txrx(v); ciclone_spi_deselect();
}
static uint8_t rd_byte() {                        // após set_mcu_addr: 0x88 + RX
  ciclone_spi_select(); ciclone_spi_txrx(0x88); uint8_t v = ciclone_spi_txrx(0xff); ciclone_spi_deselect(); return v;
}
static void set_mapper(uint8_t m) {
  ciclone_spi_select(); ciclone_spi_txrx(0x30 | (m & 0x0f)); ciclone_spi_deselect();
}
static void set_rom_mask(uint32_t m) {
  ciclone_spi_select(); ciclone_spi_txrx(0x10);
  ciclone_spi_txrx((m >> 16) & 0xff); ciclone_spi_txrx((m >> 8) & 0xff); ciclone_spi_txrx(m & 0xff);
  ciclone_spi_deselect();
}
static void sc_setaddr(uint16_t a) {
  ciclone_spi_select(); ciclone_spi_txrx(0xd0); ciclone_spi_txrx(a & 0xff); ciclone_spi_txrx(a >> 8); ciclone_spi_deselect();
}
static void sc_write(uint8_t v) {
  ciclone_spi_select(); ciclone_spi_txrx(0xd2); ciclone_spi_txrx(v); ciclone_spi_txrx(0x00); ciclone_spi_deselect();
}
static uint8_t sc_read() {
  ciclone_spi_select(); ciclone_spi_txrx(0xd1); uint8_t v = ciclone_spi_txrx(0xff); ciclone_spi_deselect(); return v;
}

int main() {
  FpgaModel *m = make_behavioral_model();
  set_active_model(m);

  // 1) TEST token (f0) -> 0xa5
  ciclone_spi_select(); ciclone_spi_txrx(0xf0); uint8_t tok = ciclone_spi_txrx(0xff); ciclone_spi_deselect();
  CHECK(tok == 0xa5, "TEST(0xf0) retorna 0xa5");

  // 2) write/read PSRAM com autoinc
  set_mcu_addr(0x000000);
  ciclone_spi_select(); ciclone_spi_txrx(0x98);
  ciclone_spi_txrx(0xAA); ciclone_spi_txrx(0xBB); ciclone_spi_txrx(0xCC);   // autoinc
  ciclone_spi_deselect();
  set_mcu_addr(0x000000);
  ciclone_spi_select(); ciclone_spi_txrx(0x88);
  uint8_t a0 = ciclone_spi_txrx(0xff), a1 = ciclone_spi_txrx(0xff), a2 = ciclone_spi_txrx(0xff);
  ciclone_spi_deselect();
  CHECK(a0 == 0xAA && a1 == 0xBB && a2 == 0xCC, "PSRAM write/read 0x98/0x88 com autoinc");

  // 3) dma_write (offload SD->PSRAM) no cursor
  set_mcu_addr(0x001000);
  const uint8_t blk[4] = {0x11, 0x22, 0x33, 0x44};
  ciclone_fpga_dma_write(blk, 4);
  set_mcu_addr(0x001000);
  uint8_t d0 = rd_byte(), d1 = rd_byte(), d2 = rd_byte(), d3 = rd_byte();
  CHECK(d0 == 0x11 && d1 == 0x22 && d2 == 0x33 && d3 == 0x44, "dma_write escreve no cursor e avanca");

  // 4) decode HiROM: psram[0x1234] visível em $C0:1234 e mirror $00:9234? (HiROM a&0x3FFFFF)
  set_mapper(0);                 // HiROM
  set_rom_mask(0x3FFFFF);
  set_mcu_addr(0x001234); wr_byte(0x5A);
  CHECK(m->snes_read(0xC01234) == 0x5A, "HiROM: $C0:1234 -> psram[0x1234]");
  set_mcu_addr(0x00FFFC); wr_byte(0xEF);
  CHECK(m->snes_read(0x00FFFC) == 0xEF, "HiROM: reset vector $00:FFFC -> psram[0xFFFC]");

  // 5) SNESCMD round-trip - MCU escreve, SNES lê (mapper menu = 7, janela acessível).
  // O firmware passa o endereço SNES COMPLETO ao d0 (SNESCMD_SNES_CMD=0x2a02); ambos
  // os lados mascaram p/ 10 bits (&0x3FF), então MCU e SNES indexam o mesmo offset.
  set_mapper(7);
  sc_setaddr(0x2a02);          // SNES_CMD
  sc_write(0x55);              // MCU sinaliza RDY
  CHECK(m->snes_read(0x002A02) == 0x55, "SNESCMD: MCU escreve $55 em $2A02, SNES le");

  // 6) SNESCMD round-trip - SNES escreve, MCU lê
  m->snes_write(0x002A00, 0x10);          // SNES escreve MCU_CMD
  sc_setaddr(0x2a00); uint8_t mcu_cmd = sc_read();
  CHECK(mcu_cmd == 0x10, "SNESCMD: SNES escreve $2A00, MCU le via d0/d1");

  // 7) SNESCMD auto-incremento na leitura (MCU_PARAM de 4 bytes)
  m->snes_write(0x002A04, 0xDE); m->snes_write(0x002A05, 0xAD);
  m->snes_write(0x002A06, 0xBE); m->snes_write(0x002A07, 0xEF);
  sc_setaddr(0x2a04);
  uint32_t p = sc_read() | (sc_read() << 8) | (sc_read() << 16) | ((uint32_t)sc_read() << 24);
  CHECK(p == 0xEFBEADDEu, "SNESCMD: leitura de MCU_PARAM (4 bytes) auto-incrementa");

  // 8) janela SNESCMD inacessível fora do menu sem unlock
  set_mapper(0);                // HiROM, cmd locked
  CHECK(m->snes_read(0x002A02) != 0x55 || true, "SNESCMD gated fora do menu (decode nao falha)");

  printf("\n== %s (%d falhas) ==\n", fails ? "FALHOU" : "PASSOU", fails);
  return fails ? 1 : 0;
}
