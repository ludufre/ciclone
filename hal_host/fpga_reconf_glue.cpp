/* Ciclone glue: C-callable FPGA reconfigure that drives the active FpgaModel.
 * Kept separate so behavioral.cpp / fpga_model.h stay untouched. */
#include "fpga_model.h"

#include <string.h>

// the core the firmware loaded, by bitstream name: 1 = the SMS core (runs as RTL in the model),
// 2 = fpga_dsp (the uPD7725 runs in bsnes's NECDSP)
extern "C" void ciclone_fpga_reconfigure(const char *core) {
  int id = core && strstr(core, "fpga_sms.") ? 1 : core && strstr(core, "fpga_dsp.") ? 2 : 0;
  if (ciclone::active_model()) ciclone::active_model()->reconfigure(id);
}
