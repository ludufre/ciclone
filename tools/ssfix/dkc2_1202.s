; key: 1202 9860
; name: dkc2 v1.0/v1.1 (US) - assembled from ciclone tools/ssfix/dkc2_1202.s (tools/ss65.py)
;|  Rare's driver holds ONE song in the APU (every scene uploads its own: JSL $B5800C, A = song)
;|  and the state does not carry the APU, so a load in another scene kept the other scene's song.
;|  On LOAD only (CS_SA1_LOAD $FE1013 = 1) replay the loaded scene's song, $001C (the game's own
;|  "current song": callers skip the call when it already matches). Not from here: the hook's
;|  $C0-$FF window hides the ROM the upload reads, so -- as dkc3_b28c.s -- it plants a one-shot NMI
;|  routine at $0110 (the never-used bottom of the stack page) and points the game's NMI dispatch
;|  ($0020) at it; the first NMI after the hook restores $0020, uploads with NMI off, waits for
;|  vblank and goes on. Must come AFTER "000000,2140" above (the sends wait for $2140 == $0000).
;
; Source of the savestate_fixes.yml entries (python3 tools/ss65.py tools/ssfix/dkc2_1202.s).
; Same engine as DKC3 (tools/ssfix/dkc3_b28c.s), other addresses, identical in v1.0 and v1.1:
;   $B58000   jump table of the sound API; $B5800C = jmp $8106: "load and play song A" (A/X 16-bit):
;             sta $1C, command $FF (driver to its loader), upload, command $FA (play)
;   NMI $00:F37D (v1.1 $F3BD) -> bank $80: rep #$30, D = 0, $2C++, then jmp ($0020)
;   $1C through the front end and the first level: title $11, select $02, mode $18, map $01,
;   Pirate Panic $06 (checked in ciclone).
; Runs from PSRAM bank $FE with A 8-bit / X 16-bit, DBR and D unknown; restores both.

CS_SA1_LOAD = $FE1013       ; 0 on the save path, 1 on the load path (snes/savestate.a65)
LAST_SONG   = $7E001C       ; the song the game is playing (its own record)
NMI_PTR     = $7E0020       ; the game's NMI dispatch: jmp ($0020) in bank $80
NMI_PTR0    = $000020       ; the same, from the NMI routine (bank $00 = WRAM)
DISPATCH    = $0020
PLAY_SONG   = $B5800C       ; "load and play song A" 
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
        cmp #$0100
        bcs out                 ; not a song number: leave it
        and #$00FF
        beq out
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

; The one-shot NMI routine, copied to $0110 and run from $80:0110 by the game's jmp ($004A):
; A/X 16-bit, D = 0 (the game's NMI prologue). Its immediates are filled in above.
        .a16
        .x16
template:
t_ptr:  lda #$0000
        sta.l NMI_PTR0          ; one shot: the scene's own NMI routine is back
        sep #$20
t_off:  lda #$00
        sta.l $004200           ; no NMI while the upload runs (the scene's routine is not reentrant)
        rep #$20
t_song: lda #$0000
        jsl PLAY_SONG           ; load and play it: outside the hook, $C0-$FF are ROM again
        sep #$20
vbl1:   lda.l $004212
        bmi vbl1                ; out of the vblank the upload may have ended in...
vbl2:   lda.l $004212
        bpl vbl2                ; ...to the start of the next one
        lda.l $004210           ; drop the pending NMI flag, or re-enabling fires one right away
t_on:   lda #$00
        sta.l $004200
        rep #$20
        jmp (DISPATCH)          ; this frame's NMI work, in vblank
tail:
end:
