; key: B28C
; name: dkc3 v1.0 (US) - assembled from ciclone tools/ssfix/dkc3_b28c.s (tools/ss65.py)
;|  Rare's driver holds ONE song in the APU (every scene uploads its own: JSL $B28009, A = song)
;|  and the state does not carry the APU, so a load in another scene kept the other scene's song.
;|  On LOAD only (CS_SA1_LOAD $FE1013 = 1) replay the loaded scene's song, $0008 (what $B2807D keeps
;|  of the last request; = $0765&$3F in a level). Not from here: the song tables are long reads
;|  from $ED/$EE, which the hook's $C0-$FF window turns into PSRAM. So it plants a one-shot NMI
;|  routine at $0110 (the never-used bottom of the stack page) and points the game's NMI dispatch
;|  ($004A) at it; the first NMI after the hook restores $004A, uploads with NMI off, waits for
;|  vblank and goes on. Must come AFTER "000006,2140" above (the sends wait for $2140 == $0006).
;
; Source of the savestate_fixes.yml entry (python3 tools/ss65.py tools/ssfix/dkc3_b28c.s).
; How it was found: README "Writing a savestate audio fix". What the game does:
;   $B28000   jump table of the sound API; $B28009 = jmp $807D: "load and play song A" (A/X 16-bit):
;             sta $08, command $FF (driver to its loader), upload, command $FA (play)
;   $B2825D   send a command: wait until $2140 echoes $06, write $2141/$2142, $2140 = ++$06
;   $B282B5.. the song's pointers come from long tables at $ED0D86.. / $EE078A..
;   NMI $00:CA45 -> $80:CA49: rep #$30, D = 0, $5A++, then jmp ($004A) = this scene's NMI routine
;   Callers pass the song per scene (map $25, Wrinkly's cabin $05); a level passes $0765&$3F.
;   $0008 is direct-page scratch in principle, but it held the scene's song through a whole
;   Lakeside Limbo run (checked in ciclone, from a player's state).
; Runs from PSRAM bank $FE with A 8-bit / X 16-bit, DBR and D unknown; restores both.

CS_SA1_LOAD = $FE1013       ; 0 on the save path, 1 on the load path (snes/savestate.a65)
LAST_SONG   = $7E0008       ; the song $B2807D was last asked for
NMI_PTR     = $7E004A       ; the game's NMI dispatch: jmp ($004A) in bank $80
NMI_PTR0    = $00004A       ; the same, from the NMI routine (bank $00 = WRAM)
DISPATCH    = $004A
PLAY_SONG   = $B28009       ; "load and play song A" 
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
        jsl PLAY_SONG           ; load and play it: outside the hook, $ED/$EE are ROM again
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
