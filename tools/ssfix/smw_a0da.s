; key: A0DA
; name: super mario world (US) - assembled from ciclone tools/ssfix/smw_a0da.s (tools/ss65.py)
;|  The state restores WRAM but not the APU, and SMW swaps the APU's music bank on every
;|  level <-> overworld change, so a load in another area left the wrong bank and a
;|  silent or wrong song. On LOAD only (CS_SA1_LOAD $FE1013 = 1; the fixes also run after a save):
;|  mode $14 (level) -> the game's own $00:8134 (level bank) + music $0DDA; mode $0E (overworld) ->
;|  $00:810E (overworld bank) + $04:8D8A[submap $1F11,$0DB3]; then $11 (pause sound) if $13D4 says
;|  paused. The RTS routines are reached through the $6B byte at $00:804D used as an RTL trampoline.
;
; Source of the savestate_fixes.yml entry (python3 tools/ss65.py tools/ssfix/smw_a0da.s).
; How it was found: README "Writing a savestate audio fix". What the game does:
;   $00:811D  "$FF -> $2141" (the driver drops to its IPL loader), upload the bank at [$00], then zero
;             $2140-$2143 and the command bytes $1DF9-$1E00. Entered from:
;   $00:8134  pick the level bank (bonus game, special levels...) then $811D  <- jsr at $00:9702
;   $00:810E  the overworld bank ($0E:98B1) then $811D                       <- jsr at $00:A0B3
;   NMI $00:816A sends $1DFB (song request) to $2142 and $1DF9/$1DFA/$1DFC to $2140/$2141/$2143.
;   Level song: $0DDA. Overworld song: $04:8D8A[submap], submap = $1F11 + player ($0DB3), as at $04:8E44.
; Runs from PSRAM bank $FE with A 8-bit / X 16-bit, DBR and D unknown: it sets both for the game's
; code and restores them. Position independent (brl/per), so it works wherever it lands after other
; entries' code.

CS_SA1_LOAD = $FE1013       ; 0 on the save path, 1 on the load path (snes/savestate.a65)
GAME_MODE   = $0100
LEVEL_SONG  = $0DDA
PLAYER      = $0DB3
SUBMAP      = $1F11
OW_SONGS    = $048D8A
PAUSED      = $13D4
SND_SFX1    = $1DF9         ; -> $2140 on the next NMI
SND_SONG    = $1DFB         ; -> $2142 on the next NMI
RTL_BYTE    = $804C         ; $00:804D holds $6B (operand of an LDA #$6B), minus 1 for RTS

        .a8
        .x16
        lda @CS_SA1_LOAD
        bne go
        brl done                ; a save: leave the music alone
go:     phb
        phd
        php
        sep #$30                ; the game's routines run with 8-bit A/X
        lda #$00
        pha
        plb                     ; DBR = $00 (the game's WRAM mirror + ROM)
        pea $0000
        pld                     ; D = 0 (they use [$00] as the upload pointer)
        lda GAME_MODE
        cmp #$14
        beq level
        cmp #$0E
        beq ow
        brl out                 ; any other mode (a transition): the game re-sends on its own
level:  phk
        per ret1-1              ; RTL frame: back to ret1 in this bank
        pea RTL_BYTE            ; RTS frame: the routine's RTS lands on $00:804D = RTL
        jml $008134             ; upload the level's music bank
ret1:   lda LEVEL_SONG
        sta SND_SONG            ; and ask for the level's song
        bra pause
ow:     phk
        per ret2-1
        pea RTL_BYTE
        jml $00810E             ; upload the overworld's music bank
ret2:   ldx PLAYER
        lda SUBMAP,x
        tax
        lda OW_SONGS,x
        sta SND_SONG            ; and ask for this submap's song
pause:  lda PAUSED
        beq out
        lda #$11
        sta SND_SFX1            ; loaded paused: the pause sound mutes it again, as on the pause screen
out:    plp
        pld
        plb
done:
