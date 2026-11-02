【客户端运行时资源】
- dvb_s2_r5_6.pchk：LDPC 校验矩阵；verify_board_result 用它检查板端回传的 syndrome。
- permutation64800：交织置换表；verify_board_result 用它将板端回传解交织到自然顺序。

历史 Windows 外部译码器 r5_6_ldpc_hard_decoder.exe 及其三个 MinGW 运行库（libgcc_s_seh-1.dll、libstdc++-6.dll、libwinpthread-1.dll）已从本包移除：当前客户端与活动工具均无调用点，且其来源与再分发许可未能确认。原文件哈希保留在 sources.json 的 removed_files 中以便追溯。

【离线工具】
- native_ldpc.hard_decode 仍供离线解码、黄金数据和数据集生成工具使用。
- libc_ldpc.so 仍由 clients/python/c_ldpc.py 使用；生成数据集、鲁棒性扫描、回归和主机性能分析工具会导入 c_ldpc。

【板端结果规则】
输入为板端回传的 64,800 个结果位。校验矩阵的 syndrome 全零才通过；任一校验行非零都判为失败，PC 端不再译码兜底。通过后按信息位生成载荷：给定 input_bytes 时按字节数截断；未给时沿用 JPEG EOI 截断，适用于原有图像判据。
