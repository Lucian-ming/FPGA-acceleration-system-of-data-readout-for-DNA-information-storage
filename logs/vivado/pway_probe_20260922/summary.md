# 7020 摸底 Vivado 结果摘要（2026-09-22）

## z010_p4
# puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"
===> 综合 srpe_batch_pway  器件 xc7z010clg400-1  时钟 100MHz (周期 10.0ns)  参数 -generic P_WAYS=4 -generic READ_BPS=150 -generic REF_LEN=957 -generic STRIDE=807 -generic NUM_LC=50
  | Slice LUTs              | 8067 |     0 |          0 |     17600 | 45.84 |
  | Slice Registers         | 6592 |     0 |          0 |     35200 | 18.73 |
  | Slice Registers                            | 6592 |     0 |          0 |     35200 | 18.73 |
  | Block RAM Tile    |    8 |     0 |          0 |        60 | 13.33 |
# puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
  WNS = 0.145 ns   (>=0 表示在 100MHz 下收敛)

## z020_p8
# puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"
===> 综合 srpe_batch_pway  器件 xc7z020clg400-1  时钟 100MHz (周期 10.0ns)  参数 -generic P_WAYS=8 -generic READ_BPS=150 -generic REF_LEN=957 -generic STRIDE=807 -generic NUM_LC=50
  | Slice LUTs              | 15666 |     0 |          0 |     53200 | 29.45 |
  | Slice Registers         |  9293 |     0 |          0 |    106400 |  8.73 |
  | Slice Registers                            |  9293 |     0 |          0 |    106400 |  8.73 |
  | Block RAM Tile    |    8 |     0 |          0 |       140 |  5.71 |
# puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
  WNS = -3.058 ns   (>=0 表示在 100MHz 下收敛)

## z020_p16
# puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"
===> 综合 srpe_batch_pway  器件 xc7z020clg400-1  时钟 100MHz (周期 10.0ns)  参数 -generic P_WAYS=16 -generic READ_BPS=150 -generic REF_LEN=957 -generic STRIDE=807 -generic NUM_LC=50
  | Slice LUTs              | 30747 |     0 |          0 |     53200 | 57.80 |
  | Slice Registers         | 15307 |     0 |          0 |    106400 | 14.39 |
  | Slice Registers                            | 15307 |     0 |          0 |    106400 | 14.39 |
  | Block RAM Tile    |    8 |     0 |          0 |       140 |  5.71 |
# puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
  WNS = -10.220 ns   (>=0 表示在 100MHz 下收敛)

## z020_p32
# puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"
===> 综合 srpe_batch_pway  器件 xc7z020clg400-1  时钟 100MHz (周期 10.0ns)  参数 -generic P_WAYS=32 -generic READ_BPS=150 -generic REF_LEN=957 -generic STRIDE=807 -generic NUM_LC=50
ERROR: [DRC UTLZ-1] Resource utilization: Slice LUTs over-utilized in Top Level Design (This design requires more Slice LUTs cells than are available in the target device. This design requires 63040 of such cell types but only 53200 compati

## z020_p8_pipe
# puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"
===> 综合 srpe_batch_pway  器件 xc7z020clg400-1  时钟 100MHz (周期 10.0ns)  参数 -generic P_WAYS=8 -generic PIPE_TREE=1 -generic READ_BPS=150 -generic REF_LEN=957 -generic STRIDE=807 -generic NUM_LC=50
  | Slice LUTs              | 14432 |     0 |          0 |     53200 | 27.13 |
  | Slice Registers         | 15256 |     0 |          0 |    106400 | 14.34 |
  | Slice Registers                            | 15256 |     0 |          0 |    106400 | 14.34 |
  | Block RAM Tile    |    8 |     0 |          0 |       140 |  5.71 |
# puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
  WNS = 0.640 ns   (>=0 表示在 100MHz 下收敛)

## z020_p16_pipe
# puts "===> 综合 $top  器件 $part_name  时钟 ${clk_mhz}MHz (周期 ${period}ns)  参数 $generics"
===> 综合 srpe_batch_pway  器件 xc7z020clg400-1  时钟 100MHz (周期 10.0ns)  参数 -generic P_WAYS=16 -generic PIPE_TREE=1 -generic READ_BPS=150 -generic REF_LEN=957 -generic STRIDE=807 -generic NUM_LC=50
  | Slice LUTs              | 26867 |     0 |          0 |     53200 | 50.50 |
  | Slice Registers         | 25829 |     0 |          0 |    106400 | 24.28 |
  | Slice Registers                            | 25829 |     0 |          0 |    106400 | 24.28 |
  | Block RAM Tile    |    8 |     0 |          0 |       140 |  5.71 |
# puts "  WNS = $wns ns   (>=0 表示在 ${clk_mhz}MHz 下收敛)"
  WNS = 0.705 ns   (>=0 表示在 100MHz 下收敛)

