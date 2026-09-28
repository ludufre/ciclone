/* Ciclone host shim for src/integer.h - shadows it via -I order.
 *
 * CRITICAL 32-vs-64-bit fix: the firmware's integer.h does
 *   typedef unsigned long DWORD;   typedef long LONG;
 * On the ARM (ILP32) target `long` is 32-bit, which is what FatFs *requires*
 * (DWORD must be exactly 32-bit: sector numbers, FAT entries, LD_DWORD reading
 * 4 bytes, and the FATFS/FIL struct field sizes all assume it). On macOS arm64
 * (LP64) `long` is 64-bit, so the real integer.h silently makes DWORD 8 bytes -
 * which corrupts every FatFs read (mount returns FR_NO_FILESYSTEM, etc.).
 *
 * Here we pin the FatFs integer types to fixed widths so the in-process firmware
 * FatFs behaves exactly as on the device. */
#ifndef _INTEGER
#define _INTEGER

#include <stdint.h>

typedef int             INT;
typedef unsigned int    UINT;

typedef char            CHAR;
typedef unsigned char   UCHAR;
typedef unsigned char   BYTE;

typedef int16_t         SHORT;
typedef uint16_t        USHORT;
typedef uint16_t        WORD;
typedef uint16_t        WCHAR;

typedef int32_t         LONG;    /* MUST be 32-bit for FatFs (not host `long`) */
typedef uint32_t        ULONG;
typedef uint32_t        DWORD;   /* MUST be 32-bit for FatFs */

#endif /* _INTEGER */
