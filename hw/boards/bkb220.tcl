# BKB220 注册占位：缺厂商原理图/preset 和实际 PCB 确认时禁止生成硬件。
# 此处料号只记录已见手册的候选，不能作为实物核验。
set board_config [dict create \
  id bkb220 ready 0 part xc7z020clg400-2 \
  pending {等待实际完整料号/PCB、PS时钟、DDR时序和板级延迟、UART MIO、PS GEM/MDIO/PHY/复位及厂商preset；禁止沿用ECO PS7}]
