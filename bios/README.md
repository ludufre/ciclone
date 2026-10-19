# bios/

Chip firmware the cartridge loads from `/sd2snes/` on a real card. The tests that need one
copy it from here onto the test card; a test whose file is missing is skipped, never failed.

| File | Used by |
|---|---|
| `dsp1b.bin` | `tests/menu/test_dsp.py` (DSP-1 program + data ROM, 8 KB) |

Put your own dumps in this folder (or point `CICLONE_BIOS` at another one). Everything here
except this README is ignored by git: chip firmware never goes into the repository.
