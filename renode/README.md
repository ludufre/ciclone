# M4 - Co-simulação com Renode (LPC1756 rodando o `.im3` real)

**Status: SCAFFOLD + avaliação honesta. NÃO é uma co-sim funcional.**

A meta do M4 é a fidelidade máxima do MCU: o Renode executa o **binário `.im3` REAL** do
LPC1756 e fala com o **mesmo `FpgaModel`** dos M2/M3 via uma ponte SPI (seam). Isso fecharia
a co-simulação de 3 núcleos (bsnes + FpgaModel + Renode-MCU).

## Por que não está pronto (e é o maior esforço do projeto)

A pesquisa de viabilidade confirmou:

- **O Renode NÃO tem a família NXP LPC17xx.** O único arquivo LPC é `lpc2294` (ARM7, núcleo
  errado). O núcleo **Cortex-M3 + NVIC + SysTick funcionam**, mas **todos** os periféricos do
  LPC176x no caminho crítico do firmware teriam que ser escritos em C#:
  **SSP0 (SPI), GPDMA, GPIO, RIT, RTC, SYSCON**.
- **USB device CDC** (FxPakPro) no Renode é **experimental**, sem solução turnkey.
- O QEMU também não tem LPC17xx; portar periféricos lá é ainda mais difícil que no Renode.

Estimativa realista: **semanas** de engenharia. Não é completável a um estado funcional numa
sessão - por isso este diretório é um ponto de partida honesto, não uma co-sim que roda.

## Caminho concreto para implementar

1. Instalar Renode (NÃO está no Homebrew): baixar do antmicro + `mono` (também ausente no host).
2. O `.im3` REAL vem do build da firmware (o mesmo que o M4 usa: `tools/fetch_m4fw.sh` traz o par
   `.im3` + `.elf` para `build/m4fw/`). Ou seja, o binário está pronto -- não precisa rebuildar aqui.
3. Implementar os periféricos LPC176x em C# (`renode/peripherals/`), começando pelo **SSP0** como
   uma PONTE: cada byte no `DR` do SSP é encaminhado por socket ao runtime do ciclone, que chama
   `ciclone_spi_txrx()` (o MESMO seam dos M2/M3) e devolve a resposta. GPIO p/ o chip-select +
   PROG_B/INIT_B/DONE/CCLK/DIN (programação do FPGA -> `model->reconfigure`).
4. `lpc1756.repl` + `sd2snes.resc` (skeletons aqui) carregam o `.im3` e conectam a ponte.
5. Verificação: o `.im3` real boota no Renode, fala SPI pelo socket, e o menu (no bsnes) +
   carga de ROM funcionam ponta-a-ponta - exatamente como no M2, mas com o binário ARM real.

## Por que a arquitetura já está pronta para isso

O seam SPI (`include/ciclone_seam.h`) foi desenhado como interface plugável: hoje o backend é
in-process (firmware-lib chamando `ciclone_spi_*` direto). O backend Renode é o MESMO seam por
socket - sem mudar o `FpgaModel` nem o chip do bsnes. Essa é a razão de o M2/M3 terem sido
construídos com o seam: o M4 pluga atrás dele.
