// CICLONE M3 - wrapper de simulação: instancia o `main` REAL do FPGA + modelos
// comportamentais de PSRAM/SRAM EM VERILOG (dentro da Verilação). Assim o barramento
// de memória resolve COMBINACIONALMENTE no mesmo eval (sem a latência de realimentação
// que o modelo em C++ introduzia e que quebrava a leitura rápida do barramento SNES).
// Expõe só os pinos SNES/SPI/controle; ROM_*/RAM_* ficam internos.

module sim_psram(
  input  [21:0] addr,
  inout  [15:0] data,
  input         oe,    // ativo-baixo
  input         we,    // ativo-baixo
  input         bhe,   // ativo-baixo (byte alto)
  input         ble    // ativo-baixo (byte baixo)
);
  reg [15:0] mem [0:4194303];   // 4M words x 16 bit
  // leitura: dirige `data` quando OE baixo e não escrevendo (PSRAM async)
  assign data = (~oe & we) ? mem[addr] : 16'bz;
  // escrita: captura enquanto WE baixo (async), honrando byte-enables
  always @(*) if (~we) begin
    if (~ble) mem[addr][7:0]  = data[7:0];
    if (~bhe) mem[addr][15:8] = data[15:8];
  end
endmodule

module sim_sram(
  input  [18:0] addr,
  inout  [7:0]  data,
  input         oe,
  input         we
);
  reg [7:0] mem [0:524287];     // 512 KB
  assign data = (~oe & we) ? mem[addr] : 8'bz;
  always @(*) if (~we) mem[addr] = data;
endmodule

module sim_top(
  input         CLKIN,
  input         SPI_MOSI,
  input         SPI_SS,
  input         SPI_SCK,
  inout         SPI_MISO,
  input  [23:0] SNES_ADDR_IN,
  input         SNES_READ_IN,
  input         SNES_WRITE_IN,
  input         SNES_ROMSEL_IN,
  input         SNES_CPU_CLK_IN,
  input         SNES_SYSCLK,
  input         SNES_REFRESH,
  input         SNES_CIC_CLK,
  input  [7:0]  SNES_PA_IN,
  input         SNES_PARD_IN,
  input         SNES_PAWR_IN,
  input         PT5_in,
  input  [3:0]  SD_DAT,
  inout  [7:0]  SNES_DATA,
  inout         SD_CMD,
  inout         SD_CLK,
  output        SNES_IRQ,
  output        SNES_DATABUS_OE,
  output        SNES_DATABUS_DIR,
  output        MCU_RDY,
  output        ROM_ZZ,
  output        PM6_out,
  output        PN6_out,
  output        DAC_MCLK,
  output        DAC_LRCK,
  output        DAC_SDOUT
);
  wire [21:0] ROM_ADDR;
  wire [15:0] ROM_DATA;
  wire        ROM_OE, ROM_WE, ROM_BHE, ROM_BLE, ROM_1CE, ROM_2CE;
  wire [18:0] RAM_ADDR;
  wire [7:0]  RAM_DATA;
  wire        RAM_OE, RAM_WE;

  main uut(
    .CLKIN(CLKIN),
    .SPI_MOSI(SPI_MOSI), .SPI_MISO(SPI_MISO), .SPI_SS(SPI_SS), .SPI_SCK(SPI_SCK),
    .SNES_ADDR_IN(SNES_ADDR_IN),
    .SNES_READ_IN(SNES_READ_IN), .SNES_WRITE_IN(SNES_WRITE_IN), .SNES_ROMSEL_IN(SNES_ROMSEL_IN),
    .SNES_CPU_CLK_IN(SNES_CPU_CLK_IN), .SNES_SYSCLK(SNES_SYSCLK), .SNES_REFRESH(SNES_REFRESH),
    .SNES_CIC_CLK(SNES_CIC_CLK), .SNES_PA_IN(SNES_PA_IN), .SNES_PARD_IN(SNES_PARD_IN),
    .SNES_PAWR_IN(SNES_PAWR_IN), .PT5_in(PT5_in), .SD_DAT(SD_DAT),
    .SNES_DATA(SNES_DATA), .SD_CMD(SD_CMD), .SD_CLK(SD_CLK),
    .SNES_IRQ(SNES_IRQ), .SNES_DATABUS_OE(SNES_DATABUS_OE), .SNES_DATABUS_DIR(SNES_DATABUS_DIR),
    .MCU_RDY(MCU_RDY), .ROM_ZZ(ROM_ZZ), .PM6_out(PM6_out), .PN6_out(PN6_out),
    .DAC_MCLK(DAC_MCLK), .DAC_LRCK(DAC_LRCK), .DAC_SDOUT(DAC_SDOUT),
    .ROM_ADDR(ROM_ADDR), .ROM_DATA(ROM_DATA),
    .ROM_OE(ROM_OE), .ROM_WE(ROM_WE), .ROM_BHE(ROM_BHE), .ROM_BLE(ROM_BLE),
    .ROM_1CE(ROM_1CE), .ROM_2CE(ROM_2CE),
    .RAM_ADDR(RAM_ADDR), .RAM_DATA(RAM_DATA), .RAM_OE(RAM_OE), .RAM_WE(RAM_WE)
  );

  sim_psram psram(.addr(ROM_ADDR), .data(ROM_DATA), .oe(ROM_OE), .we(ROM_WE), .bhe(ROM_BHE), .ble(ROM_BLE));
  sim_sram  sramm(.addr(RAM_ADDR), .data(RAM_DATA), .oe(RAM_OE), .we(RAM_WE));
endmodule
