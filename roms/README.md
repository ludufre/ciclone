# roms/

The real-game tests (`tests/menu/test_games.py`) look their ROMs up here by CRC32: any file
name, any subfolder, `.sfc`/`.smc`, with or without a 512-byte copier header. Put your own
dumps in this folder (or point `CICLONE_ROMS` at another one); a test whose ROM is missing is
skipped, never failed.

Everything in this folder except this README is ignored by git: commercial ROMs never go into
the repository.
