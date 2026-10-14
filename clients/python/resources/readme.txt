【客户端运行时资源】
- dvb_s2_r5_6.pchk：LDPC 校验矩阵；verify_board_result 用它检查板端回传的 syndrome。
- permutation64800：交织置换表；verify_board_result 用它将板端回传解交织到自然顺序。

客户端运行时不再调用 R5_6_LDPC_hard_decoder.exe，也不需要 libgcc_s_seh-1.dll、libstdc++-6.dll、libwinpthread-1.dll。它们只为旧版 Windows 外部译码器保留，不进入新的 GUI 包。

【离线工具】
- native_ldpc.hard_decode 仍供离线解码、黄金数据和数据集生成工具使用。
- libc_ldpc.so 仍由 clients/python/c_ldpc.py 使用；生成数据集、鲁棒性扫描、回归和主机性能分析工具会导入 c_ldpc。
- 当前活动工具未发现启动 R5_6_LDPC_hard_decoder.exe 或加载上述三个 MinGW DLL 的调用点。

【板端结果规则】
输入为板端回传的 64,800 个结果位。校验矩阵的 syndrome 全零才通过；任一校验行非零都判为失败，PC 端不再译码兜底。通过后按信息位生成载荷：给定 input_bytes 时按字节数截断；未给时沿用 JPEG EOI 截断，适用于原有图像判据。
