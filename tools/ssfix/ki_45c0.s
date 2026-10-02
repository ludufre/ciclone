; key: 45C0
; name: killer instinct (US) - assembled from ciclone tools/ssfix/ki_45c0.s (tools/ss65.py)
;|  The state restores WRAM but not the APU. The game keeps in WRAM which song ($17DA) and which
;|  sample pack ($B0) the APU holds and sends every command with a counter handshake ($17DC against
;|  $2140, no timeout): after a load in another scene the APU has other data, a command is never
;|  answered and the game spins forever with NMI off. Copying the port alone is not enough, and it
;|  must wait for the port to settle: a command sent just before the hook is echoed a moment later.
;|  On LOAD only (CS_SA1_LOAD $FE1013 = 1) it also asks for the loaded scene's song again through
;|  the game's own pending-song word ($AA): the NMI epilogue at $80:F253 uploads it and clears $B0.
;
; Source of the savestate_fixes.yml entry (python3 tools/ss65.py tools/ssfix/ki_45c0.s).
; What the game does:
;   $81:F49C  send a command: wait $2140 == $17DC, A -> $2141/$2142, $17DC + 1 -> $2140 and $17DC.
;   $81:F298  upload a block with the same counter, one word per handshake.
;   $81:EF6D  "play song A": nothing when A == $17DA; else $17DA = A, $AA = A and, at once or from
;             the NMI epilogue ($80:F253: lda $AA / jsl $81EF73), command $FF, the song's samples
;             and sequences, $AA = 0, $B0 = 0, command $FE.
;   $81:F3FE  a sound that lives in a sample pack sets $A8/$AE; $81:F437 uploads pack $AE when it
;             is not $B0.
; So $AA = $17DA makes the game upload the state's song on the first NMI after the hook, with its
; own code and outside the hook (the tables are in $C4, behind the hook's $C0-$FF window).
; Runs from PSRAM bank $FE with A 8-bit / X 16-bit, DBR and D unknown: long addresses only.

CS_SA1_LOAD = $FE1013       ; 0 on the save path, 1 on the load path (snes/savestate.a65)
APU0        = $002140
ECHO        = $7E17DC       ; the counter the game expects back on $2140
SONG        = $7E17DA       ; the song the game believes the APU holds
PENDING     = $7E00AA       ; song to (re)upload at the end of the next NMI

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
