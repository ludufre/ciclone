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
  // What the cart edge sees outside its own ranges (the bsnes chip's snoop hooks):
  // the CPU about to fetch an interrupt vector (native = after 4 stack pushes, the
  // pattern cheat.v detects), every bus write and the $4016 reads, the /RESET strobe,
  // and one call per SNES frame (the model's clock for multi-second timers).
  virtual void    cpu_vector_fetch(uint32_t vector, int native) { (void)vector; (void)native; }
  virtual void    snoop(uint32_t addr, uint8_t data, int write) { (void)addr; (void)data; (void)write; }
  virtual void    snes_reset_strobe() {}
  virtual void    snes_frame() {}

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

  // ---- audio do cartucho (DAC MSU-1) ----
  // O fetcher de SFX do core base (sfxdma.v, FPGA_CMD_SFX_PLAY): toca um PCM da PSRAM
  // (16-bit estéreo LE, 44100 Hz). Devolve até `frames` quadros estéreo em out[2*frames].
  virtual int      sfx_samples(int16_t *out, int frames) { (void)out; (void)frames; return 0; }
  virtual void     sfx_state(uint32_t *base, uint32_t *len) { *base = 0; *len = 0; }
  // Tudo o que o DAC toca em `frames` quadros (44100 Hz): o fetcher de SFX e o buffer de
  // 2 KB que o MCU enche por SD-DMA (música do FMV da ficha, tocador de PCM, jingle do
  // tour). O ponteiro de leitura só anda aqui: o runner chama isto a cada quadro do SNES,
  // com ou sem janela, e o bit DAC_READ_MSB do status (que o MCU usa para reabastecer)
  // segue esse relógio.
  virtual int      cart_samples(int16_t *out, int frames) { return sfx_samples(out, frames); }
  virtual void     dac_write(const uint8_t *buf, uint32_t len) { (void)buf; (void)len; }  // offload SD->DAC
  virtual int      dac_playing() { return 0; }
  virtual int      dac_loud() { return 0; }   // bytes of the 2 KB buffer that are not silence
};

// modelo ativo p/ o qual o seam C despacha
void       set_active_model(FpgaModel *m);
FpgaModel *active_model();

// fábrica do backend comportamental
FpgaModel *make_behavioral_model();

} // namespace ciclone
