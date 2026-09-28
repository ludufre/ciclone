/* Ciclone host shim - shadows the build-generated cfgware.h (the RLE-compressed
 * FPGA bitstream baked into the mk3 firmware). On the host the FPGA "program"
 * goes to the behavioral model (hal_host/fpga_host.c::fpga_pgm -> reconfigure),
 * so the real bitstream is never streamed. A tiny dummy array keeps fpga.c's
 * `sizeof(cfgware)` and rle_mem_init(cfgware, ...) compiling if ever used. */
#ifndef CICLONE_HOST_CFGWARE_H
#define CICLONE_HOST_CFGWARE_H
static const unsigned char cfgware[1] = { 0x00 };
#endif
