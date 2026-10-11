// Ciclone - the SMS core (verilog/sd2snes_sms) inside the FPGA model.
//
// The Behavioral model hands the SMS-specific part of the cart edge to this object while
// the firmware has fpga_sms loaded: the $E0-$E3 buffer window, the $EF control window
// (pad + double-buffer swap) and the SNES bus activity that competes with the core for
// the PSRAM. The implementation (sms_model.cpp) runs the REAL RTL of the core (sms_core.v
// and below, Verilated) and mirrors in C++ the glue that main.v/address.v put around it.
// Without it linked in, make_sms_core() returns nullptr and an .sms boots the player on a
// silent model (what Ciclone did before).
#pragma once
#include <stdint.h>

namespace ciclone {

class SmsCore {
public:
  virtual ~SmsCore() {}
  virtual void power_on() = 0;                       // fpga_pgm(fpga_sms): fresh core, in reset
  virtual void snes_reset() = 0;                     // /RESET: SNES_DEADr resets the core
  // SNES time, in master clocks since an arbitrary origin (monotonic)
  virtual void run_to(uint64_t mc) = 0;
  // SNES bus events at time mc (the caller passes the current SNES time)
  virtual void cart_cycle(uint64_t mc) = 0;          // a ROM_HIT bus cycle (player code, DMA from $E0)
  virtual void ctx_write(uint64_t mc) = 0;           // a write ctx.v mirrors into PSRAM
  virtual uint8_t buf_read(uint32_t addr) = 0;       // $E0-$E3: the front buffer set
  virtual void ctl_write(uint32_t addr, uint8_t d) = 0;   // $EF0000/1 pad, $EF0005 swap
  virtual void nmi(uint64_t mc) = 0;                 // the S-CPU takes its NMI (player timing)
  virtual void screen_on(uint64_t mc) = 0;           // $2100 = $0F (end of the player's NMI work)
  virtual void snes_frame(uint64_t mc) = 0;          // once per SNES frame
  // one pass of the firmware's game loop, as the host firmware ran it since the last frame:
  // PSRAM bytes it read/wrote and SPI bytes in all (0, 0 = not in its game loop)
  virtual void mcu_load(double psram_per_pass, double spi_per_pass) = 0;
  // the core's state by name: vram cram wram vreg (the VDP's and the Z80's memories), bank (the
  // Sega mapper's bank registers), pc (the Z80 address bus, 2 bytes LE); bytes copied, -1 = no such space
  virtual int peek(const char *space, uint32_t addr, uint8_t *out, int n) = 0;
  // "key=value ..." counters since power on (see sms_model.cpp for the meaning)
  virtual int stats(char *buf, int n) = 0;
};

// nullptr when Ciclone was built without the Verilated core (fpga_model/verilate_sms.sh)
SmsCore *make_sms_core(uint8_t *psram);

} // namespace ciclone
