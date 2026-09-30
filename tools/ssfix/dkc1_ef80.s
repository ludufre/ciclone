; key: EF80 D17C
; name: dkc1 v1.0/v1.1 (US) - assembled from ciclone tools/ssfix/dkc1_ef80.s (tools/ss65.py)
;|  The driver holds ONE song in the APU (every scene uploads its own through $B99036, A = song)
;|  and the state does not carry the APU, so a load in another scene kept the other scene's song.
;|  On LOAD only (CS_SA1_LOAD $FE1013 = 1) replay the loaded scene's song, $0523 (the song the
;|  game started; $FF = stopped: then nothing). As dkc3_b28c.s it runs from a one-shot NMI
;|  routine planted at $0110 (the never-used bottom of the stack page) through the game's NMI
;|  dispatch ($001C), outside the hook, with NMI off during the upload. $0521 (the song the game
;|  believes is in the APU) is invalidated first, or $B99036 would skip the upload. Must come
;|  AFTER "000000,2140" above (the sends wait for $2140 to echo $00).
;
; Source of the savestate_fixes.yml entries (python3 tools/ss65.py tools/ssfix/dkc1_ef80.s).
; Identical in v1.0 and v1.1:
;   $B99036   "play song A": stop ($B990E7: $0523 = 0, command $FF), upload A unless A == $0521
;             ($B99027 -> JSL $8AB40F), start ($B990CE: $0523 = A, sample set $8AB1C6, command $FE)
;   $8AB1AA   send a command: wait until $2140 echoes DP $00, write $2141, toggle bit 7 of $00
;   NMI $00:A968 (v1.1 $A95F) -> bank $80: rep #$30, pha/phx/phy, forced blank, jmp ($001C);
;             D and DBR are the interrupted code's, so the routine sets and restores them.
;   $0521/$0523 through the front end and the first level: select $09, map $0C, Jungle Hijinxs $00.
; Runs from PSRAM bank $FE with A 8-bit / X 16-bit, DBR and D unknown; restores both.

CS_SA1_LOAD = $FE1013       ; 0 on the save path, 1 on the load path (snes/savestate.a65)
LAST_SONG   = $7E0523       ; the song the game started ($FF: stopped)
NMI_PTR     = $7E001C       ; the game's NMI dispatch: jmp ($001C) in bank $80
NMI_PTR0    = $00001C       ; the same, from the NMI routine (bank $00 = WRAM)
DISPATCH    = $001C
IN_APU      = $0521         ; the song the game believes the APU holds
PLAY_SONG   = $B99036       ; "play song A"
OTH_4200    = $F45080       ; SRAM_OTH_BANK[0]: the game's $4200, from the loaded state
TR          = $0110         ; where the NMI routine goes (WRAM $000110 = $80:0110)

        .a8
        .x16
        lda @CS_SA1_LOAD
        bne go
        brl done                ; a save: leave the music alone
go:     phb
        phd
        php
        rep #$30
        pea $0000
        pld                     ; D = 0
        lda @LAST_SONG
        cmp #$00FF
        bcs out                 ; stopped, or not a song number: leave it
        pha
        sep #$20
        lda #$7E
        pha
        plb                     ; DBR = $7E: abs,y below lands in WRAM
        rep #$20
        per template
        plx                     ; X = the template's address (in this bank, $FE)
        ldy #$0000
copy:   lda @$FE0000,x
        sta TR,y
        inx
        inx
        iny
        iny
        cpy #tail-template
        bcc copy
        pla
        sta TR+t_song+1-template        ; the song
        lda @NMI_PTR
        sta TR+t_ptr+1-template         ; the NMI routine to go back to
        sep #$20
        lda @OTH_4200
        sta TR+t_on+1-template          ; $4200 as the game had it
        and #$7F
        sta TR+t_off+1-template         ; the same with NMI off, for the upload
        rep #$20
        lda #TR
        sta.w DISPATCH                  ; the next NMI runs it (DBR = $7E)
out:    plp
        pld
        plb
done:   bra end

; The one-shot NMI routine, copied to $0110 and run from $80:0110 by the game's jmp ($001C):
; A/X 16-bit (the NMI prologue), D and DBR the interrupted code's. Immediates filled in above.
        .a16
        .x16
template:
t_ptr:  lda #$0000
        sta.l NMI_PTR0          ; one shot: the scene's own NMI routine is back
        phb
        phd
        pea $0000
        pld                     ; D = 0 (the sends compare with DP $00)
        phk
        plb                     ; DBR = $80 (the sound code's $05xx are WRAM through it)
        sep #$20
t_off:  lda #$00
        sta.l $004200           ; no NMI while the upload runs (the scene's routine is not reentrant)
        rep #$20
        lda #$FFFF
        sta.w IN_APU            ; "nothing in the APU": the upload is not skipped
t_song: lda #$0000
        jsl PLAY_SONG           ; play it, outside the hook
        sep #$20
vbl1:   lda.l $004212
        bmi vbl1                ; out of the vblank the upload may have ended in...
vbl2:   lda.l $004212
        bpl vbl2                ; ...to the start of the next one
        lda.l $004210           ; drop the pending NMI flag, or re-enabling fires one right away
t_on:   lda #$00
        sta.l $004200
        rep #$30
        pld
        plb
        jmp (DISPATCH)          ; this frame's NMI work, in vblank
tail:
end:
