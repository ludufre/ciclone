// CICLONE M4 - emulação do LPC1756 (Cortex-M3) com Unicorn Engine, rodando o .im3 REAL.
// Caminho alternativo ao Renode/QEMU (que não têm LPC176x): emulamos o núcleo Cortex-M3
// e fazemos HOOK do MMIO dos periféricos LPC, roteando SSP -> seam SPI -> FpgaModel.
// Esta 1ª versão: carrega o .im3, roda do reset e loga os acessos a periféricos / mem
// não mapeada, para ver o firmware real executar e diagnosticar o que prover.
#include <unicorn/unicorn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

// seam SPI -> FpgaModel (behavioral.cpp / m4_glue.cpp), o MESMO dos M2/M3
extern void    ciclone_m4_init_fpga(void);
extern void    ciclone_spi_select(void);
extern void    ciclone_spi_deselect(void);
extern uint8_t ciclone_spi_txrx(uint8_t tx);

#define FLASH_BASE 0x00000000u
#define FLASH_SIZE 0x00040000u   // 256 KB
// .im3 = header 0x100 (no flash em 0xc000) + intermediate.bin (.text com VMA 0xc100,
// pois o objcopy -R .fwhdr removeu o placeholder de 0x100B). Logo im3[0x100] = flash 0xc100.
#define FW_OFF     0x0000c100u   // .text/vetores do firmware ficam em 0xc100
#define SRAM_BASE  0x10000000u
#define SRAM_SIZE  0x00008000u   // 32 KB (cobre os 16K locais)
#define AHBRAM_BASE 0x2007c000u
#define AHBRAM_SIZE 0x00004000u   // 16 KB AHB SRAM (termina em 0x20080000; sem overlap c/ GPIO MMIO)

static uint64_t g_icount = 0;
static uint32_t g_last_mmio_w_addr = 0, g_last_mmio_w_val = 0;
static int g_mmio_w_count = 0, g_mmio_r_count = 0;

static const char *periph_name(uint64_t a) {
  if (a >= 0x40088000 && a < 0x40089000) return "SSP0";
  if (a >= 0x4000c000 && a < 0x4000d000) return "UART0";
  if (a >= 0x4009c000 && a < 0x4009d000) return "UART3";
  if (a >= 0x400fc000 && a < 0x400fd000) return "SYSCON/PLL";
  if (a >= 0x2009c000 && a < 0x2009d000) return "GPIO";
  if (a >= 0x400b0000 && a < 0x400b1000) return "RIT";
  if (a >= 0x50004000 && a < 0x50005000) return "GPDMA";
  if (a >= 0x5000c000 && a < 0x5000d000) return "USB";
  if (a >= 0x4002c000 && a < 0x4002d000) return "PINCON";
  return "?";
}

// IMPORTANTE: o Unicorn passa `addr` RELATIVO ao base do mapa; o base vem em `ud`.
// leitura de MMIO: por ora devolve defaults plausíveis p/ não travar o init.
static uint64_t mmio_read(uc_engine *uc, uint64_t off, unsigned size, void *ud) {
  (void)uc; (void)size;
  uint64_t addr = (uint64_t)ud + off;   // endereço absoluto
  g_mmio_r_count++;
  // SYSCON inteiro (0x400fc000-0x400fcfff): devolve TODOS os bits "ready" (OSCSTAT/PLOCK/etc.)
  // p/ qualquer poll de status de clock passar, independente do bit/endereço exato.
  if (addr >= 0x400fc000 && addr < 0x400fd000) {
    static int n = 0; if (n++ < 8) printf("  [syscon] read 0x%llx -> all-ready\n", (unsigned long long)addr);
    return 0xffffffff;
  }
  // USB: USBClkSt (0x5000cff8) - todos os clocks USB "on" (USB_Init faz polling de &0x12==0x12)
  if (addr == 0x5000cff8) return 0x0000001f;
  // USB: USBDevIntSt (0x5000c200) - EP_RLZED(8) + CCEMPTY(4) + CDFULL(5): satisfaz os waits de init
  // e os comandos SIE, sem sinalizar eventos de dispositivo (DEV_STAT) que disparariam processamento.
  if (addr == 0x5000c200) return 0x00000130;
  // SSP0 SR (status, +0x0c): TFE(0) RNE(2) TNF(1) - pronto p/ tx/rx
  if (addr == 0x4008800c) return 0x00000003;
  // SysTick (SCS @0xe000e010): CTRL=enabled; CVR = contador livre decrescente
  if (addr == 0xe000e010) return 0x00010005;            // CTRL: ENABLE|CLKSOURCE|COUNTFLAG
  if (addr == 0xe000e018) { static uint32_t cvr = 0xffffff; cvr = (cvr - 13) & 0xffffff; return cvr; }
  return 0; // default
}
static uint64_t sys_read(uc_engine *uc, uint64_t addr, unsigned size, void *ud) {
  return mmio_read(uc, addr, size, ud);   // SysTick/NVIC/SCB tratados em mmio_read (default 0)
}
static void mmio_write(uc_engine *uc, uint64_t off, unsigned size, uint64_t val, void *ud) {
  (void)uc; (void)size;
  uint64_t addr = (uint64_t)ud + off;   // endereço absoluto (ud = base do mapa)
  g_mmio_w_count++; g_last_mmio_w_addr = (uint32_t)addr; g_last_mmio_w_val = (uint32_t)val;
  // Chip-select do FPGA = GPIO0 pino 16: FIOCLR(0x2009c01c)=baixo=select; FIOSET(0x2009c018)=alto=deselect
  if ((val & 0x10000)) {
    if (addr == 0x2009c01c) ciclone_spi_select();
    else if (addr == 0x2009c018) ciclone_spi_deselect();
  }
}

// Bit-banding do Cortex-M3 (HW que o Unicorn não emula): alias 0x22000000 -> SRAM
// 0x20000000, alias 0x42000000 -> periféricos 0x40000000. Cada palavra do alias é 1 bit.
// Traduzimos p/ byte+bit subjacente e fazemos RMW via uc_mem_read/write (roteia RAM/MMIO).
static void bb_xlate(uint64_t addr, uint64_t *target, unsigned *bit) {
  uint64_t base = (addr >= 0x42000000) ? 0x42000000 : 0x22000000;
  uint64_t region = (addr >= 0x42000000) ? 0x40000000 : 0x20000000;
  uint64_t off = addr - base;
  *target = region + (off >> 5);
  *bit = (off >> 2) & 7;
}
static uint64_t bb_read(uc_engine *uc, uint64_t off, unsigned size, void *ud) {
  (void)size; uint64_t t; unsigned bit; bb_xlate((uint64_t)ud + off, &t, &bit);
  // pinos GPIO lidos por bit-band: devolve "alto" (FPGA MCU_RDY/handshake pronto)
  if (t >= 0x2009c000 && t < 0x2009d000) return 1;
  uint8_t b = 0; uc_mem_read(uc, t, &b, 1); return (b >> bit) & 1;
}
static void bb_write(uc_engine *uc, uint64_t off, unsigned size, uint64_t val, void *ud) {
  (void)size; uint64_t t; unsigned bit; bb_xlate((uint64_t)ud + off, &t, &bit);
  uint8_t b = 0; uc_mem_read(uc, t, &b, 1);
  if (val & 1) b |= (1u << bit); else b &= ~(1u << bit);
  uc_mem_write(uc, t, &b, 1);
}

static bool unmapped_cb(uc_engine *uc, uc_mem_type type, uint64_t addr, int size, int64_t val, void *ud) {
  (void)uc; (void)size; (void)val; (void)ud;
  printf("  [unmapped %s @ 0x%08llx] após %llu instr (PC parará aqui)\n",
         type == UC_MEM_READ_UNMAPPED ? "RD" : type == UC_MEM_WRITE_UNMAPPED ? "WR" : "FETCH",
         (unsigned long long)addr, (unsigned long long)g_icount);
  return false; // para a emulação
}
// Endereços das funções/variáveis interceptadas - RESOLVIDOS do .elf em runtime,
// NÃO hardcoded: assim o emulador sobrevive a qualquer rebuild da firmware (só aponte
// p/ o .elf que casa com o .im3). Veja resolve_symbols().
typedef struct {
  uint32_t ticks, send_command_fast, file_init,
    disk_read, disk_write, disk_init, disk_stat, disk_ioctl,
    sdn_init, read_block, write_block, f_mount, fpga_pgm, load_rom,
    menu_loop, snes_loop, delay_ms, uart_putc, get_cic, spi_tx, spi_rx;
} syms_t;
static syms_t S;

static uint16_t rd16(const uint8_t *p){ return (uint16_t)(p[0] | (p[1]<<8)); }
static uint32_t rd32(const uint8_t *p){ return (uint32_t)(p[0] | (p[1]<<8) | (p[2]<<16) | ((uint32_t)p[3]<<24)); }

// Lê o symtab de um ELF32 LE e preenche S. Retorna 0 se achou os símbolos-chave.
static int resolve_symbols(const char *path) {
  FILE *f = fopen(path, "rb"); if (!f) { fprintf(stderr, "nao abriu elf %s\n", path); return -1; }
  fseek(f,0,SEEK_END); long n=ftell(f); fseek(f,0,SEEK_SET);
  uint8_t *e = malloc(n); if (fread(e,1,n,f)!=(size_t)n) { fclose(f); free(e); return -1; } fclose(f);
  if (memcmp(e, "\177ELF", 4)) { fprintf(stderr, "%s nao e ELF\n", path); free(e); return -2; }
  uint32_t shoff = rd32(e+0x20); uint16_t shent = rd16(e+0x2e), shnum = rd16(e+0x30);
  const uint8_t *sym=0; uint32_t symsz=0, syment=0; const char *str=0;
  for (uint16_t i=0; i<shnum; i++) {
    const uint8_t *sh = e + shoff + (uint32_t)i*shent;
    if (rd32(sh+4) == 2) {  // SHT_SYMTAB
      sym = e + rd32(sh+0x10); symsz = rd32(sh+0x14); syment = rd32(sh+0x24);
      const uint8_t *shs = e + shoff + rd32(sh+0x18)*shent; str = (const char*)(e + rd32(shs+0x10));
    }
  }
  if (!sym || !str || !syment) { fprintf(stderr, "symtab ausente em %s (build sem simbolos?)\n", path); free(e); return -3; }
  for (uint32_t o=0; o+syment<=symsz; o+=syment) {
    const uint8_t *s = sym + o; const char *nm = str + rd32(s+0); uint32_t v = rd32(s+4);
    #define MF(name,field) if (!strcmp(nm,name)) S.field = v & ~1u;   // função thumb: limpa bit0
    #define MD(name,field) if (!strcmp(nm,name)) S.field = v;          // dado
    MD("ticks",ticks)
    MF("send_command_fast",send_command_fast) MF("file_init",file_init)
    MF("disk_read",disk_read) MF("disk_write",disk_write) MF("disk_initialize",disk_init)
    MF("disk_status",disk_stat) MF("disk_ioctl",disk_ioctl) MF("sdn_init",sdn_init)
    MF("read_block",read_block) MF("write_block",write_block) MF("f_mount",f_mount)
    MF("fpga_pgm",fpga_pgm) MF("load_rom",load_rom) MF("menu_main_loop",menu_loop)
    MF("snes_main_loop",snes_loop) MF("delay_ms",delay_ms) MF("uart_putc",uart_putc)
    MF("get_cic_state",get_cic) MF("spi_tx_byte",spi_tx) MF("spi_rx_byte",spi_rx)
    #undef MF
    #undef MD
  }
  free(e);
  return (S.menu_loop && S.disk_read && S.uart_putc && S.spi_tx) ? 0 : -4;  // achou os principais?
}

static uint8_t *g_sd = NULL; static long g_sd_size = 0;   // imagem do SD (build/sdcard.img)
static int g_seen_mount = 0, g_seen_pgm = 0, g_seen_load = 0, g_uart_started = 0;
static int g_disk_reads = 0;

static void ret_from(uc_engine *uc, uint32_t r0) {   // "return" da função: r0 + PC=LR
  uint32_t lr = 0; uc_reg_read(uc, UC_ARM_REG_LR, &lr);
  uc_reg_write(uc, UC_ARM_REG_R0, &r0);
  uc_reg_write(uc, UC_ARM_REG_PC, &lr);
}

// Intercepta funções no nível de PC (endereços resolvidos do .elf em S): SD nativo/bit-bang
// servido do sdcard.img (semihosting), delays/UART dirigidos por ISR, CIC ausente, e o SPI
// do FPGA roteado ao FpgaModel. Símbolo não-resolvido = 0, e o PC nunca é 0 -> nunca casa.
static void code_cb(uc_engine *uc, uint64_t addr, uint32_t size, void *ud) {
  (void)size; (void)ud;
  if ((++g_icount % 2000) == 0) { uint32_t t=0; uc_mem_read(uc,S.ticks,&t,4); t++; uc_mem_write(uc,S.ticks,&t,4); }
  uint32_t a = (uint32_t)addr;

  if (a == S.send_command_fast) {  // comando SD nativo - serve resposta/dados do sdcard.img
    uint32_t cmdp=0, rsp=0, buf=0;
    uc_reg_read(uc,UC_ARM_REG_R0,&cmdp); uc_reg_read(uc,UC_ARM_REG_R1,&rsp); uc_reg_read(uc,UC_ARM_REG_R2,&buf);
    uint8_t c0=0; uc_mem_read(uc, cmdp, &c0, 1); int cmdno=c0 & 0x3f;
    uint8_t ab[4]={0}; uc_mem_read(uc, cmdp+1, ab, 4); uint32_t arg=(ab[0]<<24)|(ab[1]<<16)|(ab[2]<<8)|ab[3];
    uint8_t r[6]={0}; if (rsp) uc_mem_write(uc, rsp, r, 6);          // R1=0 (pronto)
    if (buf && (cmdno==17||cmdno==18||cmdno==51)) { long off=(long)arg*512; if(g_sd&&off+512<=g_sd_size) uc_mem_write(uc,buf,g_sd+off,512); }
    ret_from(uc, 0); return;
  }
  if (a == S.read_block) {  // void read_block(sector r0, buf r1) - serve do sdcard.img
    uint32_t sector=0, buf=0; uc_reg_read(uc,UC_ARM_REG_R0,&sector); uc_reg_read(uc,UC_ARM_REG_R1,&buf);
    long off=(long)sector*512; if (g_sd && off+512<=g_sd_size) uc_mem_write(uc, buf, g_sd+off, 512);
    if (g_disk_reads++ < 4) printf("  [boot] read_block sector=%u -> servido do sdcard.img\n", sector);
    uint32_t lr=0; uc_reg_read(uc,UC_ARM_REG_LR,&lr); uc_reg_write(uc,UC_ARM_REG_PC,&lr); return;
  }
  if (a == S.write_block) {
    uint32_t sector=0, buf=0; uc_reg_read(uc,UC_ARM_REG_R0,&sector); uc_reg_read(uc,UC_ARM_REG_R1,&buf);
    long off=(long)sector*512; if (g_sd && off+512<=g_sd_size) uc_mem_read(uc, buf, g_sd+off, 512);
    uint32_t lr=0; uc_reg_read(uc,UC_ARM_REG_LR,&lr); uc_reg_write(uc,UC_ARM_REG_PC,&lr); return;
  }
  if (a == S.delay_ms) { uint32_t lr=0; uc_reg_read(uc,UC_ARM_REG_LR,&lr); uc_reg_write(uc,UC_ARM_REG_PC,&lr); return; }
  if (a == S.spi_tx) { uint32_t b=0; uc_reg_read(uc,UC_ARM_REG_R0,&b); ciclone_spi_txrx((uint8_t)b);  // -> FpgaModel
                       uint32_t lr=0; uc_reg_read(uc,UC_ARM_REG_LR,&lr); uc_reg_write(uc,UC_ARM_REG_PC,&lr); return; }
  if (a == S.spi_rx) { uint32_t r = ciclone_spi_txrx(0xff);           // resposta do FpgaModel
                       uc_reg_write(uc,UC_ARM_REG_R0,&r); uint32_t lr=0; uc_reg_read(uc,UC_ARM_REG_LR,&lr); uc_reg_write(uc,UC_ARM_REG_PC,&lr); return; }
  if (a == S.uart_putc) { uint32_t c=0; uc_reg_read(uc,UC_ARM_REG_R0,&c);  // log de boot -> stdout
    if (!g_uart_started){ g_uart_started=1; printf("  ---- UART do firmware ----\n"); }
    { int ch=(int)(c&0xff); putchar(ch); if (ch=='\n') fflush(stdout); }
    uint32_t lr=0; uc_reg_read(uc,UC_ARM_REG_LR,&lr); uc_reg_write(uc,UC_ARM_REG_PC,&lr); return; }
  if (a == S.sdn_init)  { printf("  [boot] sdn_init (power-up SD nativo) -> OK (interceptado)\n"); ret_from(uc, 0); return; }
  if (a == S.disk_init) { printf("  [boot] disk_initialize -> OK\n"); ret_from(uc, 0); return; }
  if (a == S.disk_stat) { ret_from(uc, 0); return; }
  if (a == S.disk_ioctl){ ret_from(uc, 0); return; }
  if (a == S.disk_read) {  // r0=drv r1=buff r2=sector r3=count -> serve do sdcard.img
    uint32_t buff=0, sector=0, count=0;
    uc_reg_read(uc,UC_ARM_REG_R1,&buff); uc_reg_read(uc,UC_ARM_REG_R2,&sector); uc_reg_read(uc,UC_ARM_REG_R3,&count);
    for (uint32_t i=0;i<count;i++){ long off=(long)(sector+i)*512; if(g_sd&&off+512<=g_sd_size) uc_mem_write(uc,buff+i*512,g_sd+off,512); }
    if (g_disk_reads++ < 4) printf("  [boot] disk_read sector=%u count=%u -> servido do sdcard.img\n", sector, count);
    ret_from(uc, 0); return;
  }
  if (a == S.disk_write) {
    uint32_t buff=0, sector=0, count=0;
    uc_reg_read(uc,UC_ARM_REG_R1,&buff); uc_reg_read(uc,UC_ARM_REG_R2,&sector); uc_reg_read(uc,UC_ARM_REG_R3,&count);
    for (uint32_t i=0;i<count;i++){ long off=(long)(sector+i)*512; if(g_sd&&off+512<=g_sd_size) uc_mem_read(uc,buff+i*512,g_sd+off,512); }
    ret_from(uc, 0); return;
  }
  if (a == S.f_mount)  { if(!g_seen_mount){g_seen_mount=1; printf("  [boot] f_mount (monta FAT do SD)\n");} return; }
  if (a == S.fpga_pgm) { if(!g_seen_pgm){g_seen_pgm=1; printf("  [boot] fpga_pgm -> OK (FPGA = FpgaModel via SSP)\n");} ret_from(uc, 0); return; }
  if (a == S.load_rom) { if(!g_seen_load){g_seen_load=1; printf("  [boot] load_rom (carrega o menu)\n");} return; }
  if (a == S.get_cic)  { static int o=0; if(!o){o=1; printf("  [boot] get_cic_state -> 3 (SNES viria do bsnes no co-sim)\n");} ret_from(uc, 3); return; }
  if (a == S.menu_loop){ printf("  [boot] *** menu_main_loop ALCANCADO *** (firmware no command loop!)\n"); uc_emu_stop(uc); return; }
  if (a == S.snes_loop){ printf("  [boot] *** snes_main_loop ALCANCADO *** (command loop operacional!)\n"); uc_emu_stop(uc); return; }
}

int main(int argc, char **argv) {
  const char *im3 = argc > 1 ? argv[1] : "build/m4fw/firmware.im3";
  FILE *f = fopen(im3, "rb");
  if (!f) { fprintf(stderr, "nao abriu %s\n", im3); return 2; }
  fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t *buf = malloc(sz); fread(buf, 1, sz, f); fclose(f);
  // .im3 = header 0x100 (SNS3) + firmware (imagem de flash a partir de 0xc000)
  uint8_t *fw = buf + 0x100; long fwsz = sz - 0x100;
  printf("im3=%s  size=%ld  fw=%ld bytes @flash 0x%x\n", im3, sz, fwsz, FW_OFF);

  // Resolve os endereços das funções do .elf que CASA com o .im3 (argv[2], ou derivado:
  // <dir do .im3>/sd2snes-intermediate.elf). Nada é hardcoded -> sobrevive a rebuilds.
  const char *elf = argc > 2 ? argv[2] : NULL;
  char elfbuf[1024];
  if (!elf) {
    snprintf(elfbuf, sizeof elfbuf, "%s", im3);
    char *sl = strrchr(elfbuf, '/');
    if (sl) snprintf(sl+1, (size_t)(sizeof elfbuf - (sl+1-elfbuf)), "sd2snes-intermediate.elf");
    else    snprintf(elfbuf, sizeof elfbuf, "sd2snes-intermediate.elf");
    elf = elfbuf;
  }
  if (resolve_symbols(elf) != 0) {
    fprintf(stderr, "FALHA resolvendo simbolos de %s\n"
                    "  passe o .elf que casa com o .im3:  build/lpc_emu <im3> <elf>\n", elf);
    return 3;
  }
  printf("simbolos resolvidos de %s\n  menu_main_loop=0x%x disk_read=0x%x uart_putc=0x%x spi_tx=0x%x\n",
         elf, S.menu_loop, S.disk_read, S.uart_putc, S.spi_tx);

  uc_engine *uc;
  uc_err e = uc_open(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS, &uc);
  if (e) { fprintf(stderr, "uc_open: %s\n", uc_strerror(e)); return 1; }
  uc_ctl_set_cpu_model(uc, UC_CPU_ARM_CORTEX_M3);   // núcleo Cortex-M3 (M-profile)
  { uint32_t cpsr; uc_reg_read(uc, UC_ARM_REG_CPSR, &cpsr); cpsr |= 0x20; // bit T = Thumb
    uc_reg_write(uc, UC_ARM_REG_CPSR, &cpsr); }

  uc_mem_map(uc, FLASH_BASE, FLASH_SIZE, UC_PROT_ALL);
  uc_mem_map(uc, SRAM_BASE, SRAM_SIZE, UC_PROT_ALL);
  uc_mem_map(uc, AHBRAM_BASE, AHBRAM_SIZE, UC_PROT_ALL);
  uc_mem_write(uc, FW_OFF, fw, fwsz);
  // O reset M-class lê SP/PC da tabela de vetores em VTOR (=0 no reset). A tabela do
  // firmware está em 0xc000; espelhamos os primeiros 0x200 bytes em 0x0 p/ o reset achar.
  uc_mem_write(uc, 0x0, fw, fwsz < 0x200 ? fwsz : 0x200);

  // periféricos LPC como MMIO (hooks)
  // user_data = base do mapa (o Unicorn passa addr RELATIVO; reconstruímos o absoluto)
  uc_mmio_map(uc, 0x40000000, 0x00100000, mmio_read,(void*)0x40000000, mmio_write,(void*)0x40000000); // APB0/APB1
  uc_mmio_map(uc, 0x50000000, 0x00100000, mmio_read,(void*)0x50000000, mmio_write,(void*)0x50000000); // AHB (GPDMA/USB)
  uc_mmio_map(uc, 0x20080000, 0x00020000, mmio_read,(void*)0x20080000, mmio_write,(void*)0x20080000); // GPIO
  uc_mmio_map(uc, 0x22000000, 0x02000000, bb_read,(void*)0x22000000, bb_write,(void*)0x22000000);     // bit-band SRAM/GPIO
  uc_mmio_map(uc, 0x42000000, 0x02000000, bb_read,(void*)0x42000000, bb_write,(void*)0x42000000);     // bit-band periféricos
  uc_mmio_map(uc, 0xe0000000, 0x00100000, sys_read,(void*)0xe0000000, mmio_write,(void*)0xe0000000);  // SysTick/NVIC/SCB

  uc_hook h1, h2;
  uc_hook_add(uc, &h1, UC_HOOK_MEM_UNMAPPED, (void *)unmapped_cb, NULL, 1, 0);
  uc_hook_add(uc, &h2, UC_HOOK_CODE, (void *)code_cb, NULL, 1, 0);

  // SELF-TEST: confirma que o Unicorn executa Thumb neste setup (escreve 'nop;b .' @0x30000)
  { uint8_t tb[] = { 0x00,0xbf, 0x00,0xbf, 0xfe,0xe7 };  // nop; nop; b .
    uint32_t test_sp = 0x10004000; uc_mem_write(uc, 0x30000, tb, sizeof(tb));
    uc_reg_write(uc, UC_ARM_REG_SP, &test_sp);
    uint64_t before = g_icount;
    uc_err se = uc_emu_start(uc, 0x30000 | 1, 0, 0, 20);   // bit thumb no endereço de início
    printf("self-test thumb: %s, exec=%llu instr (esperado ~20)\n", uc_strerror(se),
           (unsigned long long)(g_icount - before));
  }

  // vetores do firmware (no início da imagem @0xc000): SP em +0, reset em +4
  uint32_t sp, pc;
  uc_mem_read(uc, FW_OFF + 0, &sp, 4);
  uc_mem_read(uc, FW_OFF + 4, &pc, 4);
  printf("reset: SP=0x%08x  PC=0x%08x\n", sp, pc);
  uc_reg_write(uc, UC_ARM_REG_SP, &sp);

  // imagem do SD (mesma do M2) p/ servir disk_read/initialize via interceptação de função
  FILE *sf = fopen("build/sdcard.img", "rb");
  if (sf) { fseek(sf,0,SEEK_END); g_sd_size=ftell(sf); fseek(sf,0,SEEK_SET);
            g_sd=malloc(g_sd_size); fread(g_sd,1,g_sd_size,sf); fclose(sf);
            printf("sdcard.img: %ld bytes (servido via interceptacao de disk_*)\n", g_sd_size); }
  else printf("AVISO: build/sdcard.img ausente - SD nao sera servido\n");

  ciclone_m4_init_fpga();   // FpgaModel comportamental (M2/M3) atrás do seam SPI
  printf("FpgaModel comportamental ativo (SSP do firmware -> seam -> FpgaModel)\n");

  e = uc_emu_start(uc, pc | 1u, 0, 0, 2000000000); // bit thumb; até 300M instr (ou para no main loop)
  uint32_t end_pc = 0; uc_reg_read(uc, UC_ARM_REG_PC, &end_pc);
  printf("\nparou: %s | instr=%llu | PC=0x%08x\n", uc_strerror(e), (unsigned long long)g_icount, end_pc);
  printf("MMIO: %d leituras, %d escritas (última WR 0x%08x = 0x%08x [%s])\n",
         g_mmio_r_count, g_mmio_w_count, g_last_mmio_w_addr, g_last_mmio_w_val, periph_name(g_last_mmio_w_addr));
  int reached = (end_pc == S.menu_loop || end_pc == S.snes_loop);
  printf("== %s ==\n", reached ? "firmware REAL bootou ate o command loop (M4 OK)"
                               : "firmware REAL executou no emulador (M4 core)");
  return 0;
}
