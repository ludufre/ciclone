; key: 850A
; name: killer instinct (EU) - assembled from ciclone tools/ssfix/ki_850a.s (tools/ss65.py)
;|  The state restores WRAM but not the APU. The game keeps in WRAM which song ($17DC) and which
;|  sample pack ($B1) the APU holds and sends every command with a counter handshake ($17DE against
;|  $2140, no timeout): after a load in another scene the APU has other data, a command is never
;|  answered and the game spins forever with NMI off. Copying the port alone is not enough, and it
;|  must wait for the port to settle: a command sent just before the hook is echoed a moment later.
;|  On LOAD only (CS_SA1_LOAD $FE1013 = 1) it also asks for the loaded scene's song again through
;|  the game's own pending-song word ($AB): the NMI epilogue near $80:F225 uploads it and clears $B1.
;
; Source of the savestate_fixes.yml entry (python3 tools/ss65.py tools/ssfix/ki_850a.s).
; Same driver and same fix as tools/ssfix/ki_45c0.s (read that one for what the game does); this
; revision only moves things: send $81:F47C, play song $81:EF4D, song $17DC, echo $17DE, pending $AB.
; Runs from PSRAM bank $FE with A 8-bit / X 16-bit, DBR and D unknown: long addresses only.

CS_SA1_LOAD = $FE1013       ; 0 on the save path, 1 on the load path (snes/savestate.a65)
APU0        = $002140
ECHO        = $7E17DE       ; the counter the game expects back on $2140
SONG        = $7E17DC       ; the song the game believes the APU holds
PENDING     = $7E00AB       ; song to (re)upload at the end of the next NMI

        .a8
        .x16
        php
        rep #$10
        sep #$20
        phx
        phy
        ldy #$0020              ; give up after 32 changes: never hang the hook on a noisy port
again:  lda @APU0
        dey
        beq take
        ldx #$4000              ; the port has to hold this value for ~50 ms
hold:   cmp @APU0
        bne again
        dex
        bne hold
take:   sta @ECHO
        lda @CS_SA1_LOAD
        beq out                 ; a save: the APU still matches the game, leave the song alone
        rep #$20
        lda @SONG
        sta @PENDING
        sep #$20
out:    ply
        plx
        plp
