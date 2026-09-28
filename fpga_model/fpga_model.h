// Ciclone - interface do modelo de FPGA (seam #2).
// Dois backends plugáveis implementam isto: (A) comportamental C++ (behavioral.cpp),
// (B) Verilated (M3). O chip sd2snes do bsnes chama o lado-SNES; o seam SPI chama o lado-MCU.
#pragma once
#include <stdint.h>

namespace ciclone {

class FpgaModel {
public:
  virtual ~FpgaModel() {}

  // ---- lado SNES (chamado pelo chip sd2snes do bsnes) ----
  virtual uint8_t snes_read(uint32_t addr) = 0;     // addr de 24 bits do barramento
  virtual void    snes_write(uint32_t addr, uint8_t data) = 0;
  virtual void    tick(int clocks) { (void)clocks; }

  // ---- lado MCU (chamado pelo seam SPI) ----
  virtual void    spi_select() = 0;
  virtual void    spi_deselect() = 0;
  virtual uint8_t spi_txrx(uint8_t tx) = 0;
  virtual int     mcu_rdy() { return 1; }
  virtual void    dma_write(const uint8_t *buf, uint32_t len) = 0;  // offload SD->PSRAM no cursor

  // ---- ciclo de vida ----
  virtual void    reset() {}
  virtual void    reconfigure(int core) { (void)core; }  // fpga_pgm: troca core/mapper, zera SNESCMD

  // ---- introspecção (testes/debug) ----
  virtual uint8_t *psram_ptr() { return nullptr; }
  virtual uint8_t  peek_snescmd(uint16_t off) { (void)off; return 0; }
  virtual uint8_t  mapper() { return 0; }
};

// modelo ativo p/ o qual o seam C despacha
void       set_active_model(FpgaModel *m);
FpgaModel *active_model();

// fábrica do backend comportamental
FpgaModel *make_behavioral_model();

} // namespace ciclone
