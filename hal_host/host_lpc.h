/* Ciclone host shim - stand-in for <arm/NXP/LPC17xx/LPC17xx.h> (CONFIG_MCU_H).
 *
 * The firmware includes the CMSIS device header via `#include CONFIG_MCU_H`
 * (config.h, memory.h). On the host we point CONFIG_MCU_H here instead so the
 * firmware compiles WITHOUT the real LPC17xx register map: every peripheral
 * "pointer" becomes a harmless integer sentinel and every register field a
 * member of a dummy struct that nobody dereferences (all GPIO macros are
 * neutralised in config.h, and BITBAND becomes a constant-1 mock).
 *
 * The ONLY register access the firmware really cares about on the host is the
 * FPGA chip-select (FPGA_SSREG/FPGA_SSBIT == LPC_GPIO0 bit 16). config.h turns
 * SET_BIT/CLEAR_BIT on exactly that (reg,bit) into ciclone_spi_deselect/select;
 * everything else is a no-op. So these struct fields exist only to satisfy the
 * compiler when the firmware writes e.g. reg->FIODIR (the writes hit the dummy).
 */
#ifndef CICLONE_HOST_LPC_H
#define CICLONE_HOST_LPC_H

#include <stdint.h>

/* CMSIS type qualifiers (real header: core_cm3.h) */
#ifndef __I
#define __I  volatile const
#endif
#ifndef __O
#define __O  volatile
#endif
#ifndef __IO
#define __IO volatile
#endif

/* CMSIS intrinsics -> no-ops on the host */
#ifndef __NOP
#define __NOP()  do {} while (0)
#endif
#ifndef __DSB
#define __DSB()  do {} while (0)
#endif
#ifndef __WFI
#define __WFI()  do {} while (0)
#endif
#ifndef __enable_irq
#define __enable_irq()  do {} while (0)
#endif
#ifndef __disable_irq
#define __disable_irq() do {} while (0)
#endif

/* A dummy GPIO register block. The unions in the real LPC_GPIO_TypeDef let the
 * firmware touch FIODIR / FIOSET / FIOCLR / FIOPIN[01] / FIOMASK[01]; provide
 * all of them as plain members so any reg->FIO* write/read compiles. Reads of
 * GPIO_I (== FIOPIN) go through BITBAND (constant 1), not these members. */
typedef struct {
  __IO uint32_t FIODIR;
  uint32_t RESERVED0[3];
  union { __IO uint32_t FIOMASK; struct { __IO uint8_t FIOMASK0, FIOMASK1, FIOMASK2, FIOMASK3; }; };
  union { __IO uint32_t FIOPIN;  struct { __IO uint8_t FIOPIN0,  FIOPIN1,  FIOPIN2,  FIOPIN3;  }; };
  union { __IO uint32_t FIOSET;  struct { __IO uint8_t FIOSET0,  FIOSET1,  FIOSET2,  FIOSET3;  }; };
  union { __O  uint32_t FIOCLR;  struct { __O  uint8_t FIOCLR0,  FIOCLR1,  FIOCLR2,  FIOCLR3;  }; };
} LPC_GPIO_TypeDef;

/* Minimal stand-ins for the few other peripheral structs the firmware names. */
typedef struct { __IO uint32_t SR; __IO uint32_t DR; __IO uint32_t CR0; __IO uint32_t CR1; } LPC_SSP_TypeDef;
typedef struct { __IO uint32_t PCONP; __IO uint32_t PCLKSEL0; __IO uint32_t PCLKSEL1; } LPC_SC_TypeDef;
typedef struct { __IO uint32_t MR0, MR1, MR2, MR3, MR4, MR5; __IO uint32_t MCR; __IO uint32_t EMR; } LPC_TIM_TypeDef;
typedef struct { __IO uint32_t MR0, MR1, MR2, MR3, MR4, MR5; } LPC_PWM_TypeDef;
typedef struct { __IO uint32_t PINSEL0; __IO uint32_t PINMODE0; __IO uint32_t PINMODE2; __IO uint32_t PINMODE_OD0; } LPC_PINCON_TypeDef;
typedef struct { __IO uint32_t CONFIG; } LPC_GPDMACH_TypeDef;

/* The firmware uses these as opaque "which register" tokens. We give each GPIO
 * bank a DISTINCT sentinel value so config.h's SET_BIT/CLEAR_BIT can recognise
 * the FPGA chip-select bank (LPC_GPIO0) without colliding with the others.
 * They are never dereferenced as real pointers on the host. */
extern LPC_GPIO_TypeDef    ciclone_gpio_bank[5];
extern LPC_SSP_TypeDef     ciclone_ssp0;
extern LPC_SC_TypeDef      ciclone_sc;
extern LPC_TIM_TypeDef     ciclone_tim3;
extern LPC_PWM_TypeDef     ciclone_pwm1;
extern LPC_PINCON_TypeDef  ciclone_pincon;
extern LPC_GPDMACH_TypeDef ciclone_gpdmach0;

#define LPC_GPIO0   (&ciclone_gpio_bank[0])
#define LPC_GPIO1   (&ciclone_gpio_bank[1])
#define LPC_GPIO2   (&ciclone_gpio_bank[2])
#define LPC_GPIO3   (&ciclone_gpio_bank[3])
#define LPC_GPIO4   (&ciclone_gpio_bank[4])
#define LPC_SSP0    (&ciclone_ssp0)
#define LPC_SC      (&ciclone_sc)
#define LPC_TIM3    (&ciclone_tim3)
#define LPC_PWM1    (&ciclone_pwm1)
#define LPC_PINCON  (&ciclone_pincon)
#define LPC_GPDMACH0 (&ciclone_gpdmach0)

#define LPC_PINCON_BASE ((uintptr_t)&ciclone_pincon)

#endif /* CICLONE_HOST_LPC_H */
