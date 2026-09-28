/* Ciclone glue: C-callable FPGA reconfigure that drives the active FpgaModel.
 * Kept separate so behavioral.cpp / fpga_model.h stay untouched. */
#include "fpga_model.h"

extern "C" void ciclone_fpga_reconfigure(const char *core) {
  (void)core;
  if (ciclone::active_model()) ciclone::active_model()->reconfigure(0);
}
