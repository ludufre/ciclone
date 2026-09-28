// CICLONE M3: stub comportamental generico de altsyncram (megafunction Altera).
// Modelo de RAM dual-port p/ simulacao. Cobre os modos usados pelos wrappers do
// sd2snes (snescmd_buf, bram, msu_databuf, dac_buf): BIDIR_DUAL_PORT / DUAL_PORT /
// SINGLE_PORT, ambas as portas no clock0. Saida registrada (outdata_reg=CLOCK0).
// NOTA: read-during-write tratado como "old data" simples; nuances NEW_DATA podem
// divergir marginalmente do hardware (a validar no golden trace A-vs-B).
module altsyncram #(
  parameter operation_mode = "BIDIR_DUAL_PORT",
  parameter width_a = 8,
  parameter widthad_a = 10,
  parameter numwords_a = 1024,
  parameter width_b = 8,
  parameter widthad_b = 10,
  parameter numwords_b = 1024,
  parameter width_byteena_a = 1,
  parameter width_byteena_b = 1,
  parameter outdata_reg_a = "CLOCK0",
  parameter outdata_reg_b = "CLOCK0",
  parameter address_reg_b = "CLOCK0",
  parameter indata_reg_b = "CLOCK0",
  parameter read_during_write_mode_mixed_ports = "OLD_DATA",
  parameter read_during_write_mode_port_a = "NEW_DATA_NO_NBE_READ",
  parameter read_during_write_mode_port_b = "NEW_DATA_NO_NBE_READ",
  parameter address_aclr_b = "NONE",
  parameter outdata_aclr_a = "NONE",
  parameter outdata_aclr_b = "NONE",
  parameter clock_enable_input_a = "BYPASS",
  parameter clock_enable_input_b = "BYPASS",
  parameter clock_enable_output_a = "BYPASS",
  parameter clock_enable_output_b = "BYPASS",
  parameter power_up_uninitialized = "FALSE",
  parameter wrcontrol_wraddress_reg_b = "CLOCK0",
  parameter intended_device_family = "Cyclone IV E",
  parameter lpm_type = "altsyncram",
  parameter init_file = ""
) (
  input  [widthad_a-1:0]        address_a,
  input  [widthad_b-1:0]        address_b,
  input                         clock0,
  input                         clock1,
  input  [width_a-1:0]          data_a,
  input  [width_b-1:0]          data_b,
  input                         wren_a,
  input                         wren_b,
  output reg [width_a-1:0]      q_a,
  output reg [width_b-1:0]      q_b,
  input                         aclr0,
  input                         aclr1,
  input                         addressstall_a,
  input                         addressstall_b,
  input  [width_byteena_a-1:0]  byteena_a,
  input  [width_byteena_b-1:0]  byteena_b,
  input                         clocken0,
  input                         clocken1,
  input                         clocken2,
  input                         clocken3,
  output                        eccstatus,
  input                         rden_a,
  input                         rden_b
);
  // memória largura A; assume portas simétricas (caso dos BRAMs do sd2snes)
  localparam DEPTH = (numwords_a > numwords_b) ? numwords_a : numwords_b;
  reg [width_a-1:0] mem [0:DEPTH-1];

  // Porta A (leitura/escrita no clock0)
  always @(posedge clock0) begin
    if (wren_a) mem[address_a] <= data_a;
    q_a <= mem[address_a];
  end

  // Porta B (leitura sempre; escrita só em BIDIR_DUAL_PORT)
  always @(posedge clock0) begin
    if (wren_b) mem[address_b] <= data_b[width_a-1:0];
    q_b <= mem[address_b];
  end

  assign eccstatus = 1'b0;
endmodule
