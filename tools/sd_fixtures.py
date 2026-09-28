#!/usr/bin/env python3
"""Ciclone -- arvore de teste para o SD (build/sd_fixtures/).

Cobre os casos do browser que a firmware trata de forma diferente:
  /Test Game.sfc                ROM solta na raiz
  /MSU Game/                    pasta que abre como jogo (1 ROM + <stem>.msu + faixas .pcm)
  /Two Games/                   pasta comum (2 ROMs -> abre normal mesmo com .msu)
  /Empty Folder/                pasta vazia
As ROMs sao LoROM minimas (header valido em $7FC0, codigo = loop infinito): o menu
lista, mostra a ficha e o menu de contexto; bootar mostra tela preta, o que e esperado.
"""
import os, shutil, struct, sys

def lorom(title: str, chipset: int = 0x00, mapmode: int = 0x20) -> bytes:
    """chipset = byte $FFD6 (ex.: $13/$14/$15/$1A = Super FX); mapmode = $FFD5."""
    rom = bytearray(b"\xff" * 0x20000)          # 128 KB
    rom[0:3] = b"\x80\xfe\xea"                    # bra * (loop infinito) + nop
    hdr = 0x7FC0
    rom[hdr:hdr + 21] = title.encode("ascii")[:21].ljust(21, b" ")
    rom[hdr + 0x15] = mapmode                     # $20 = LoROM, slow
    rom[hdr + 0x16] = chipset                     # $00 = ROM only
    rom[hdr + 0x17] = 0x07                        # 128 KB
    rom[hdr + 0x18] = 0x00                        # sem SRAM
    rom[hdr + 0x19] = 0x01                        # USA
    rom[hdr + 0x1A] = 0x33
    rom[hdr + 0x1B] = 0x00
    rom[0x7FFC:0x7FFE] = struct.pack("<H", 0x8000)  # reset vector -> $8000 (offset 0)
    s = sum(rom) & 0xFFFF
    # checksum + complemento (sum ja inclui os 4 bytes em $FF; o delta e pequeno, basta 1 passo)
    rom[hdr + 0x1C:hdr + 0x1E] = struct.pack("<H", s ^ 0xFFFF)
    rom[hdr + 0x1E:hdr + 0x20] = struct.pack("<H", s)
    return bytes(rom)

def main(out: str) -> None:
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    open(os.path.join(out, "Test Game.sfc"), "wb").write(lorom("CICLONE TEST GAME"))
    msu = os.path.join(out, "MSU Game")
    os.makedirs(msu)
    open(os.path.join(msu, "msugame.sfc"), "wb").write(lorom("CICLONE MSU GAME"))
    open(os.path.join(msu, "msugame.msu"), "wb").write(b"\0" * 16)
    for n in (1, 2, 10):
        open(os.path.join(msu, f"msugame-{n}.pcm"), "wb").write(b"MSU1" + b"\0" * 1020)
    two = os.path.join(out, "Two Games")
    os.makedirs(two)
    open(os.path.join(two, "first.sfc"), "wb").write(lorom("CICLONE FIRST"))
    open(os.path.join(two, "second.sfc"), "wb").write(lorom("CICLONE SECOND"))
    open(os.path.join(two, "first.msu"), "wb").write(b"\0" * 16)
    os.makedirs(os.path.join(out, "Empty Folder"))
    print(f"OK: {out}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/sd_fixtures")
