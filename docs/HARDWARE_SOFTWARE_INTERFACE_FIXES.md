# Hardware-Software Interface Fixes

## Overview
This document describes the critical hardware-software register map conflicts that were identified and fixed in the DNA information storage FPGA acceleration system.

## Critical Issues Fixed

### 1. ✅ DECODER Register Map Mismatch (CRITICAL - FIXED)

**Problem:**
The software register definitions in `sw/app/echo.h` did not match the actual hardware register map in `hw/ip/desparsification_decoder_1_0/hdl/desparsification_decoder_v1_0_S00_AXI.v`.

**Old Software Register Map (INCORRECT):**
```c
#define DECODER_REG_IN_ADDR         0x00U   // ❌ WRONG
#define DECODER_REG_IN_BEATS        0x04U   // ❌ DOESN'T EXIST
#define DECODER_REG_OUT_ADDR        0x08U   // ❌ WRONG
#define DECODER_REG_OUT_BEATS       0x0CU   // ❌ DOESN'T EXIST
#define DECODER_REG_START           0x10U   // ❌ WRONG
#define DECODER_REG_STATUS          0x18U   // ❌ WRONG
```

**Actual Hardware Register Map:**
```verilog
localparam ADDR_CTRL      = 6'h00;   // Control/Start register
localparam ADDR_STATUS    = 6'h04;   // Status register (IDLE, DONE)
localparam ADDR_IN_L      = 6'h10;   // Input address LOW 32-bits
localparam ADDR_IN_H      = 6'h14;   // Input address HIGH 32-bits
localparam ADDR_OUT_L     = 6'h18;   // Output address LOW 32-bits
localparam ADDR_OUT_H     = 6'h1C;   // Output address HIGH 32-bits
```

**New Software Register Map (CORRECT):**
```c
#define DECODER_REG_CTRL            0x00U   // ✓ Control/Start register
#define DECODER_REG_STATUS          0x04U   // ✓ Status register (FIXED from 0x18)
#define DECODER_REG_IN_ADDR_L       0x10U   // ✓ Input address LOW 32-bits
#define DECODER_REG_IN_ADDR_H       0x14U   // ✓ Input address HIGH 32-bits
#define DECODER_REG_OUT_ADDR_L      0x18U   // ✓ Output address LOW 32-bits
#define DECODER_REG_OUT_ADDR_H      0x1CU   // ✓ Output address HIGH 32-bits
```

**Impact:**
- **STATUS register mismatch**: Software was reading address 0x18 (OUT_ADDR_L) instead of actual STATUS at 0x04, causing infinite wait loops and timeouts
- **Missing IN_BEATS/OUT_BEATS registers**: Software tried to configure non-existent registers, which had no effect on hardware
- **32-bit address only**: Software only wrote lower 32-bits of addresses, upper 32-bits were always 0

**Files Modified:**
- `sw/app/echo.h` - Updated register definitions
- `sw/app/echo.c` - Updated decoder configuration to write 64-bit addresses properly, removed BEATS register writes
- `sw/app/main.c` - Updated force_decoder_to_idle() function

### 2. ✅ 64-bit Address Handling (CRITICAL - FIXED)

**Problem:**
Hardware expects 64-bit DDR addresses split into two 32-bit registers (HIGH/LOW), but software only wrote the lower 32-bits.

**Old Code (INCORRECT):**
```c
write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  DEC_IN_ADDR);   // Only lower 32 bits
write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, DEC_OUT_ADDR);  // Only lower 32 bits
```

**New Code (CORRECT):**
```c
// Write 64-bit addresses split into HIGH/LOW
write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR_H,  (u32)(((u64)DEC_IN_ADDR) >> 32));
write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR_L,  (u32)(DEC_IN_ADDR & 0xFFFFFFFF));

write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR_H, (u32)(((u64)DEC_OUT_ADDR) >> 32));
write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR_L, (u32)(DEC_OUT_ADDR & 0xFFFFFFFF));
```

**Impact:**
If any DDR address had non-zero upper 32 bits, the hardware would use incorrect addresses, leading to data corruption or system hangs.

### 3. ✅ Memory Barriers (CRITICAL - FIXED)

**Problem:**
Cache flush operations were not followed by proper memory barriers before triggering hardware, potentially causing hardware to read stale data.

**Fix:**
Added explicit memory barriers after cache flushes:
```c
Xil_DCacheFlushRange(DEC_OUT_ADDR, DEC_OUT_BEATS * 8);

/* Memory barrier to ensure cache flush completes */
__asm__ volatile("dsb sy");
__asm__ volatile("isb");
```

### 4. ✅ VOTER Register Map (VERIFIED - NO ISSUES)

**Hardware Register Map:**
```verilog
0x00: CTRL_STATUS   // Control/Status register
0x04: IN_ADDR       // Input DDR address (32-bit)
0x08: IN_BEATS      // Input beat count
0x0C: OUT_ADDR      // Output DDR address (32-bit)
0x10: OUT_BEATS     // Output beat count
0x14: TOTAL_READS   // Total number of reads to process
```

**Software Register Map:**
```c
#define VOTER_REG_CTRL_STATUS       0x00U  // ✓ MATCHES
#define VOTER_REG_IN_ADDR           0x04U  // ✓ MATCHES
#define VOTER_REG_IN_BEATS          0x08U  // ✓ MATCHES
#define VOTER_REG_OUT_ADDR          0x0CU  // ✓ MATCHES
#define VOTER_REG_OUT_BEATS         0x10U  // ✓ MATCHES
#define VOTER_REG_TOTAL_READS       0x14U  // ✓ MATCHES
```

**Status:** ✅ NO ISSUES - Software and hardware match perfectly.

**Note:** VOTER uses 32-bit addresses (not 64-bit like DECODER), which is correct for the current system where all addresses fit in 32 bits.

## Summary of Changes

| Component | Issue | Status | Files Modified |
|-----------|-------|--------|----------------|
| DECODER | STATUS register at wrong address | ✅ FIXED | echo.h, echo.c, main.c |
| DECODER | Missing 64-bit address handling | ✅ FIXED | echo.h, echo.c, main.c |
| DECODER | Non-existent BEATS registers | ✅ FIXED | echo.h, echo.c, main.c |
| All | Missing memory barriers | ✅ FIXED | echo.c |
| VOTER | Register map verification | ✅ VERIFIED | No changes needed |

## Testing Recommendations

1. **DECODER functionality test:**
   - Verify status register reads correctly (should show IDLE=1 initially)
   - Verify 64-bit addresses are written correctly to hardware
   - Test with addresses that have non-zero upper 32 bits
   - Verify decoder completes without timeouts

2. **Memory coherency test:**
   - Verify hardware sees correct data after cache flushes
   - Test with various data patterns

3. **Full pipeline test:**
   - Run complete DNA acceleration pipeline
   - Verify all three stages complete successfully
   - Check output data integrity

## Potential Remaining Issues

### VOTER IN_BEATS Calculation

The software currently calculates:
```c
const u32 VOTER_IN_BEATS = TOTAL_READS * 6u;  // = 648000 beats
```

This assumes IN_BEATS represents "total number of 64-bit beats to read", where each read consists of 6 u64s (48 bytes).

**To verify:** Check if the hardware interprets IN_BEATS as:
- Option A: Total number of 64-bit beats (current software assumption)
- Option B: Number of reads (where each read is automatically 6 u64s)

If Option B is correct, the software should be changed to:
```c
const u32 VOTER_IN_BEATS = TOTAL_READS;  // Let hardware handle 6 u64s per read
```

**Files to check:**
- `hw/ip/differential_voter_1_0/hdl/differential_voter_v1_0.v` - Read state machine
- Test with actual hardware to verify correct behavior

## References

- Hardware IP cores: `hw/ip/*/hdl/*.v`
- Software application: `sw/app/echo.c`, `sw/app/echo.h`, `sw/app/main.c`
- System documentation: `README.md`
