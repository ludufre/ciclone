// CICLONE M4 - glue C++ entre o harness Unicorn (C) e o FpgaModel (C++ do M2/M3).
// Cria/ativa o modelo comportamental; o seam ciclone_spi_* (behavioral.cpp) despacha p/ ele.
#include "fpga_model.h"

extern "C" void ciclone_m4_init_fpga(void) {
  ciclone::set_active_model(ciclone::make_behavioral_model());
}
